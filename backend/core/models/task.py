from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERTED = "reverted"


class ActionType(str, enum.Enum):
    SHELL_COMMAND = "shell_command"
    FILE_WRITE = "file_write"
    FILE_READ = "file_read"
    API_CALL = "api_call"
    CODE_PATCH = "code_patch"


class Subtask(BaseModel):
    id: str = Field(default_factory=lambda: f"subtask_{uuid.uuid4().hex[:12]}")
    description: str
    tool: ActionType
    parameters: dict = Field(default_factory=dict)
    order: int = 0
    risk_tier: Optional[str] = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    subtasks: list[Subtask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    token_usage: int = 0
    token_budget: int = 100_000
    error_message: Optional[str] = None
