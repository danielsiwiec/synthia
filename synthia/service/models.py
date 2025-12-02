from typing import Any

from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    response_schema: dict[str, Any] | None = None
    resume: bool = False
    thread_id: str | None = None


class TaskResponse(BaseModel):
    result: Any
    session_id: str


class TaskCompletion(BaseModel):
    session_id: str


class AdminNotification(BaseModel):
    content: str


class ProgressNotification(BaseModel):
    session_id: str
    summary: str
    thread_id: str | None = None


class TaskTrigger(BaseModel):
    task: str
    name: str
