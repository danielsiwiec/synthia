import asyncio

from fastapi import APIRouter, HTTPException, Request

from synthia.service.models import TaskRequest, TaskResponse
from synthia.service.task import TaskService

router = APIRouter()


@router.post("/task", response_model=TaskResponse)
async def task(request: Request, task_request: TaskRequest) -> TaskResponse:
    task_service: TaskService = request.app.state.task_service
    try:
        return await task_service.process_task(task_request)
    except asyncio.CancelledError:
        raise HTTPException(status_code=499, detail="Task was cancelled") from None


@router.post("/stop")
async def stop(request: Request, thread_id: int):
    task_service: TaskService = request.app.state.task_service
    await task_service.stop_task(thread_id)
