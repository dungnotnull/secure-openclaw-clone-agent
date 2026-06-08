from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.db.database import get_db
from backend.core.llm.provider import LLMFallbackChain
from backend.core.models.action import ActionRecord, ActionStatus, RiskTier
from backend.core.models.ledger import (
    InverseActionDescriptor,
    InverseActionType,
    LedgerEntry,
)
from backend.core.models.task import ActionType, Subtask, Task, TaskStatus
from backend.core.sandbox.executor import DockerExecutor
from backend.core.security.risk_classifier import get_risk_classifier
from backend.core.snapshot.engine import SnapshotEngine
from backend.core.snapshot.ledger import ActionLedger

logger = logging.getLogger(__name__)

TOOL_REGISTRY: dict[str, dict] = {
    "shell_command": {
        "name": "run_shell_command",
        "description": "Execute a shell command inside a sandboxed Docker container.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                },
            },
            "required": ["command"],
        },
    },
    "file_write": {
        "name": "write_file",
        "description": "Write content to a file in the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path in workspace."},
                "content": {"type": "string", "description": "File content to write."},
            },
            "required": ["path", "content"],
        },
    },
    "file_read": {
        "name": "read_file",
        "description": "Read a file from the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path in workspace."},
            },
            "required": ["path"],
        },
    },
    "api_call": {
        "name": "call_api",
        "description": "Make an HTTP API call (requires network allowlisting).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API endpoint URL."},
                "method": {"type": "string", "default": "GET"},
                "headers": {"type": "object"},
                "body": {"type": "string"},
            },
            "required": ["url"],
        },
    },
    "code_patch": {
        "name": "apply_patch",
        "description": "Apply a code patch (unified diff) to a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "patch": {"type": "string"},
            },
            "required": ["path", "patch"],
        },
    },
}

PLANNER_SYSTEM_PROMPT = """You are a task planning agent for SecureClawAgent, a security-hardened AI task runtime.

Given a user instruction, break it down into an ordered list of subtasks.
Each subtask must use exactly one tool from the available tool set.
Return your plan as a JSON array of objects with these fields:
- "description": a clear, one-line description of what this step does
- "tool": one of the tool names from the list
- "parameters": an object with the tool's required parameters
- "order": integer starting from 1

Available tools:
{tools_description}

Return ONLY the JSON array, no other text."""


class TaskOrchestrator:
    def __init__(
        self,
        *,
        llm_chain: LLMFallbackChain | None = None,
        executor: DockerExecutor | None = None,
        snapshot: SnapshotEngine | None = None,
        ledger: ActionLedger | None = None,
        workspace_dir: Path | None = None,
    ) -> None:
        self._llm_chain = llm_chain or LLMFallbackChain()
        self._executor = executor or DockerExecutor()
        self._snapshot = snapshot or SnapshotEngine(workspace_dir)
        self._ledger = ledger
        self._risk_classifier = get_risk_classifier()
        self._workspace = workspace_dir or settings.WORKSPACE_DIR
        self._db = get_db()

    async def run_task(self, task: Task) -> Task:
        task.status = TaskStatus.PLANNING
        self._db.update_task(task)

        try:
            subtasks = await self._plan(task.instruction)
            task.subtasks = subtasks
            self._db.update_task(task)
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error_message = f"Planning failed: {exc}"
            self._db.update_task(task)
            return task

        task.status = TaskStatus.RUNNING
        self._db.update_task(task)

        for subtask in sorted(task.subtasks, key=lambda s: s.order):
            if task.token_usage >= task.token_budget:
                task.error_message = "Token budget exceeded"
                task.status = TaskStatus.FAILED
                self._db.update_task(task)
                return task

            action = ActionRecord(
                task_id=task.id,
                subtask_id=subtask.id,
                action_type=subtask.tool.value,
                parameters=subtask.parameters,
            )
            action.risk_tier = self._risk_classifier.classify(action)

            if action.risk_tier in (RiskTier.HIGH_RISK_DESTRUCTIVE, RiskTier.NETWORK_EGRESS):
                task.status = TaskStatus.AWAITING_CONFIRMATION
                self._db.update_task(task)

            await self._execute_action(task, subtask, action)

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        self._db.update_task(task)
        return task

    async def run_single_action(self, task: Task, subtask: Subtask, action: ActionRecord) -> ActionRecord:
        return await self._execute_action(task, subtask, action)

    async def _plan(self, instruction: str) -> list[Subtask]:
        tools_desc = json_dumps(TOOL_REGISTRY)
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT.format(tools_description=tools_desc)},
            {"role": "user", "content": instruction},
        ]
        result = await self._llm_chain.complete(messages)
        content = result.get("content", "").strip()
        content = content.lstrip("```json").lstrip("```").rstrip("```").strip()
        raw = json.loads(content)
        return [Subtask(**item) for item in raw]

    async def _execute_action(self, task: Task, subtask: Subtask, action: ActionRecord) -> ActionRecord:
        action.status = ActionStatus.SNAPSHOTTING
        action.started_at = datetime.now(timezone.utc)

        pre_hash = self._snapshot.capture()
        action.pre_state_hash = pre_hash

        action.status = ActionStatus.RUNNING

        try:
            exit_code, stdout, stderr = self._executor.run(
                self._build_command(subtask),
                workspace_mount=self._workspace,
                network_allowed=(action.risk_tier == RiskTier.NETWORK_EGRESS),
            )
            action.exit_code = exit_code
            action.stdout = stdout[:50000]
            action.stderr = stderr[:50000]
            action.status = ActionStatus.COMPLETED if exit_code == 0 else ActionStatus.FAILED
        except Exception as exc:
            action.stderr = str(exc)
            action.exit_code = -1
            action.status = ActionStatus.FAILED

        action.completed_at = datetime.now(timezone.utc)
        diff = self._snapshot.compute_diff()
        action.diff = diff
        action.post_state_hash = self._snapshot.capture()

        action.inverse_action = self._compute_inverse(subtask, action).model_dump()

        task.token_usage += self._estimate_tokens(action)
        self._db.update_task(task)

        if self._ledger:
            hmac_key = hashlib.sha256(settings.JWT_SECRET.encode()).digest()
            entry = LedgerEntry(
                action_id=action.id,
                task_id=task.id,
                action_type=action.action_type,
                pre_state_hash=action.pre_state_hash or "",
                post_state_hash=action.post_state_hash,
                diff=action.diff,
                inverse_action=InverseActionDescriptor(**action.inverse_action)
                if isinstance(action.inverse_action, dict)
                else action.inverse_action,
                hmac_signature=None,
            )
            entry.hmac_signature = hmac.new(
                hmac_key,
                f"{entry.action_id}|{entry.task_id}|{entry.pre_state_hash}|{entry.inverse_action.model_dump_json()}".encode(),
                hashlib.sha256,
            ).hexdigest()
            self._ledger.insert(entry)

        return action

    @staticmethod
    def _build_command(subtask: Subtask) -> str:
        tool = subtask.tool
        params = subtask.parameters
        if tool == ActionType.SHELL_COMMAND:
            return params.get("command", "echo 'no command'")
        elif tool == ActionType.FILE_WRITE:
            path = params.get("path", "/workspace/output.txt")
            content = params.get("content", "")
            return f"cat > {sh_escape(path)} << 'SECURECLAW_EOF'\n{content}\nSECURECLAW_EOF"
        elif tool == ActionType.FILE_READ:
            path = params.get("path", "/workspace/input.txt")
            return f"cat {sh_escape(path)}"
        elif tool == ActionType.CODE_PATCH:
            path = params.get("path", "/workspace/patch.diff")
            patch = params.get("patch", "")
            return f"cat > {sh_escape(path)} << 'SECURECLAW_EOF'\n{patch}\nSECURECLAW_EOF && patch -p1 < {sh_escape(path)}"
        elif tool == ActionType.API_CALL:
            url = params.get("url", "")
            method = params.get("method", "GET").upper()
            return f"curl -s -X {method} {sh_escape(url)}"
        return "echo 'unknown tool'"

    @staticmethod
    def _compute_inverse(subtask: Subtask, action: ActionRecord) -> InverseActionDescriptor:
        if subtask.tool == ActionType.FILE_READ:
            return InverseActionDescriptor(
                action_type=InverseActionType.FILE_RESTORE,
                description="Revert file reads require no action",
            )
        elif subtask.tool == ActionType.FILE_WRITE:
            return InverseActionDescriptor(
                action_type=InverseActionType.FILE_RESTORE,
                description=f"Restore workspace to pre-state hash {action.pre_state_hash}",
                payload={"pre_state_hash": action.pre_state_hash or ""},
            )
        elif subtask.tool == ActionType.SHELL_COMMAND:
            return InverseActionDescriptor(
                action_type=InverseActionType.UNDO_SCRIPT,
                description="Restore workspace from pre-action snapshot",
                payload={"pre_state_hash": action.pre_state_hash or ""},
            )
        elif subtask.tool == ActionType.API_CALL:
            return InverseActionDescriptor(
                action_type=InverseActionType.COMPENSATING_API,
                description="API calls may require manual compensating transaction",
                payload={"api_url": subtask.parameters.get("url", "")},
            )
        elif subtask.tool == ActionType.CODE_PATCH:
            return InverseActionDescriptor(
                action_type=InverseActionType.FILE_RESTORE,
                description=f"Reverse patch by restoring to pre-state hash {action.pre_state_hash}",
                payload={"pre_state_hash": action.pre_state_hash or ""},
            )
        return InverseActionDescriptor(
            action_type=InverseActionType.MANUAL_REQUIRED,
            description="Unknown action type; manual revert required",
        )

    @staticmethod
    def _estimate_tokens(action: ActionRecord) -> int:
        return len(str(action.stdout or "")) // 4 + len(str(action.stderr or "")) // 4 + 10


def json_dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def sh_escape(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"
