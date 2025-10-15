from typing import Any

from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    response_schema: dict[str, Any] | None = None
    resume: bool = False


class TaskResponse(BaseModel):
    result: Any
    session_id: str


class TaskCompletion(BaseModel):
    session_id: str
    agent_name: str | None
