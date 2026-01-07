from typing import Any

from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    response_schema: dict[str, Any] | None = None
    thread_id: int
    audio_mode: bool = False


class TaskResponse(BaseModel):
    thread_id: int
    result: Any
    session_id: str


class AdminNotification(BaseModel):
    content: str
    silent: bool = False


class ProgressNotification(BaseModel):
    session_id: str
    summary: str
    thread_id: int | None = None


class TaskTrigger(BaseModel):
    task: str
    name: str
    silent: bool = False


class StopTaskRequest(BaseModel):
    thread_id: int


class ImageCreated(BaseModel):
    thread_id: int
    filename: str
