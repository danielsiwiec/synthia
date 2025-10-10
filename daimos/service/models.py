from typing import Any

from pydantic import BaseModel


class TaskRequest(BaseModel):
    task: str
    response_schema: dict[str, Any] | None = None
    resume: str | None = None


class TaskResponse(BaseModel):
    result: Any
    session_id: str
