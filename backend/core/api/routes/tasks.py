from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.background.runner import get_background_runner
from backend.core.config import settings
from backend.core.db.database import get_db
from backend.core.middleware.security import get_current_user
from backend.core.models.task import Task, TaskStatus
from backend.core.orchestrator.engine import TaskOrchestrator

router = APIRouter(tags=["tasks"])


class TaskCreateRequest(BaseModel):
    instruction: str
    token_budget: int | None = None


@router.post("/tasks", response_model=Task)
async def create_task(
    body: TaskCreateRequest,
    user_id: str = Depends(get_current_user),
):
    db = get_db()
    task = Task(
        instruction=body.instruction,
        token_budget=body.token_budget or settings.TASK_TOKEN_BUDGET,
    )
    db.create_task(task)

    runner = get_background_runner()
    orchestrator = TaskOrchestrator()
    await runner.enqueue(orchestrator.run_task, task)

    return task


@router.get("/tasks", response_model=list[Task])
async def list_tasks(
    user_id: str = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
):
    db = get_db()
    return db.list_tasks(limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(
    task_id: str,
    user_id: str = Depends(get_current_user),
):
    db = get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks/{task_id}/run", response_model=Task)
async def run_task(
    task_id: str,
    user_id: str = Depends(get_current_user),
):
    db = get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    runner = get_background_runner()
    orchestrator = TaskOrchestrator()
    await runner.enqueue(orchestrator.run_task, task)
    return task


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, user_id: str = Depends(get_current_user)):
    db = get_db()
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    from fastapi.responses import StreamingResponse
    import asyncio
    import json

    async def event_stream():
        last_status = None
        while True:
            task = db.get_task(task_id)
            if task is None:
                break
            current_status = task.status.value
            if current_status != last_status:
                last_status = current_status
                data = task.model_dump(mode="json")
                yield f"data: {json.dumps(data)}\n\n"
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REVERTED):
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
