from typing import Any

from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    thread_id: int


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


class AppStartup(BaseModel):
    pass
