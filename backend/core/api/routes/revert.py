from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.db.database import get_db
from backend.core.middleware.security import get_current_user
from backend.core.revert.engine import RevertEngine
from backend.core.snapshot.engine import SnapshotEngine
from backend.core.snapshot.ledger import ActionLedger

logger = logging.getLogger(__name__)
router = APIRouter(tags=["revert"])


def _get_revert_engine() -> RevertEngine:
    from backend.core.config import settings
    import hashlib

    snapshot = SnapshotEngine()
    hmac_key = hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    ledger = ActionLedger(db_path=settings.DB_PATH, hmac_key=hmac_key)
    ledger.open(pragma_key=settings.DB_PRAGMA_KEY or None)
    return RevertEngine(snapshot, ledger)


@router.post("/tasks/{task_id}/revert")
async def revert_task(
    task_id: str,
    user_id: str = Depends(get_current_user),
):
    db = get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    engine = _get_revert_engine()
    reverted_actions = engine.revert_task(task_id)

    from backend.core.models.task import TaskStatus
    task.status = TaskStatus.REVERTED
    db.update_task(task)

    return {
        "task_id": task_id,
        "status": "reverted",
        "reverted_actions": reverted_actions,
        "count": len(reverted_actions),
    }


@router.post("/actions/{action_id}/revert")
async def revert_action(
    action_id: str,
    user_id: str = Depends(get_current_user),
):
    engine = _get_revert_engine()
    try:
        ok = engine.revert_action(action_id)
        return {
            "action_id": action_id,
            "status": "reverted" if ok else "revert_failed",
        }
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/tasks/{task_id}/ledger/export")
async def export_ledger(
    task_id: str,
    user_id: str = Depends(get_current_user),
):
    db = get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    jsonl = db.export_ledger_jsonl(task_id)
    if not jsonl:
        raise HTTPException(status_code=404, detail="No ledger entries found for this task")

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=jsonl,
        media_type="application/jsonl",
        headers={"Content-Disposition": f"attachment; filename=ledger-{task_id}.jsonl"},
    )
