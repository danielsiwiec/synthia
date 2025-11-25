from typing import Any

from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    user: str | None = None
    response_schema: dict[str, Any] | None = None
    resume: bool = False


class TaskResponse(BaseModel):
    result: Any
    session_id: str


class TaskCompletion(BaseModel):
    session_id: str


class ProgressNotification(BaseModel):
    session_id: str
    summary: str
    user: str | None = None
