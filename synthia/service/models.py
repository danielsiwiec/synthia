from typing import Any

from pydantic import BaseModel

VISION_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/heic", "image/heif"})


class TaskImage(BaseModel):
    path: str
    content_type: str


class TaskRequest(BaseModel):
    task: str
    thread_id: int
    images: list[TaskImage] = []
    persona: str | None = None


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


class OutgoingImage(BaseModel):
    thread_id: int
    source_path: str
    name: str
    content_type: str
    caption: str = ""


class ProjectSelected(BaseModel):
    thread_id: int
    project_id: str
    name: str = ""


class TaskTrigger(BaseModel):
    task: str
    name: str
    silent: bool = False


class StopTaskRequest(BaseModel):
    thread_id: int


class AppStartup(BaseModel):
    pass
