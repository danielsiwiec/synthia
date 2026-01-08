import asyncio

from fastapi import APIRouter, HTTPException, Request

from synthia.service.models import TaskRequest, TaskResponse
from synthia.service.task import TaskService
from synthia.telemetry import current_span

router = APIRouter()


def _truncate_task(task: str, max_len: int = 200) -> str:
    return task[:max_len] if len(task) <= max_len else task[: max_len - 3] + "..."


@router.post("/task", response_model=TaskResponse)
async def task(request: Request, task_request: TaskRequest) -> TaskResponse:
    current_span().update_name(_truncate_task(task_request.task))
    task_service: TaskService = request.app.state.task_service
    try:
        return await task_service.process_task(task_request)
    except asyncio.CancelledError:
        raise HTTPException(status_code=499, detail="Task was cancelled") from None


@router.post("/stop")
async def stop(request: Request, thread_id: int):
    task_service: TaskService = request.app.state.task_service
    await task_service.stop_task(thread_id)
