import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel

from synthia.helpers.pubsub import pubsub
from synthia.service.chat import ChatService
from synthia.service.models import VISION_MIME_TYPES, StopTaskRequest, TaskImage, TaskRequest

router = APIRouter()

_static_dir = Path(__file__).parent.parent / "static"
_app_index = _static_dir / "app" / "index.html"


class _Attachment(BaseModel):
    name: str
    content_type: str = ""
    data: str


class _SendMessageRequest(BaseModel):
    content: str
    reaction: str | None = None
    attachments: list[_Attachment] | None = None


class _UpdateThreadRequest(BaseModel):
    title: str


def _serialize(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "hex"):
        return str(obj)
    return obj


def _attachment_type(content_type: str) -> str:
    if content_type.startswith("image/"):
        return "image"
    if content_type == "application/pdf" or content_type.startswith("text/"):
        return "document"
    return "file"


def _attachments_from_metadata(thread_id: int, message_id, metadata: dict | None) -> list[dict] | None:
    if not metadata or not metadata.get("attachments"):
        return None
    return [
        {
            "id": f"{message_id}-{i}",
            "type": _attachment_type(a.get("content_type", "")),
            "name": a["name"],
            "content_type": a.get("content_type", ""),
            "url": f"/chat/threads/{thread_id}/attachments/{a['file']}",
        }
        for i, a in enumerate(metadata["attachments"])
        if a.get("file")
    ]


@router.get("/chat")
async def chat_ui():
    return FileResponse(_app_index, headers={"Cache-Control": "no-cache"})


@router.get("/chat/threads")
async def list_threads(request: Request):
    chat_service: ChatService = request.app.state.chat_service
    threads = await chat_service.repository.list_threads()
    return [
        {
            "id": str(t["id"]),
            "title": t["title"],
            "created_at": t["created_at"].isoformat() if t["created_at"] else None,
            "updated_at": t["updated_at"].isoformat() if t["updated_at"] else None,
        }
        for t in threads
    ]


@router.patch("/chat/threads/{thread_id}")
async def update_thread(request: Request, thread_id: int, body: _UpdateThreadRequest):
    chat_service: ChatService = request.app.state.chat_service
    title = body.title.strip()[:100]
    if not title:
        raise HTTPException(status_code=400, detail="Title must not be empty")
    await chat_service.repository.update_thread_title(thread_id, title)
    return {"ok": True}


@router.delete("/chat/threads/{thread_id}")
async def delete_thread(request: Request, thread_id: int):
    chat_service: ChatService = request.app.state.chat_service
    await chat_service.repository.delete_thread(thread_id)
    return {"ok": True}


@router.get("/chat/threads/{thread_id}/messages")
async def get_messages(request: Request, thread_id: int):
    chat_service: ChatService = request.app.state.chat_service
    messages = await chat_service.repository.get_messages(thread_id)
    result = []
    for m in messages:
        metadata = json.loads(m["metadata"]) if m["metadata"] else None
        result.append(
            {
                "id": str(m["id"]),
                "thread_id": str(m["thread_id"]),
                "role": m["role"],
                "message_type": m["message_type"],
                "content": m["content"],
                "metadata": metadata,
                "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                "attachments": _attachments_from_metadata(thread_id, m["id"], metadata),
            }
        )
    return result


@router.get("/chat/threads/{thread_id}/attachments/{filename}")
async def get_attachment(request: Request, thread_id: int, filename: str):
    chat_service: ChatService = request.app.state.chat_service
    path = chat_service.attachment_path(thread_id, filename)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(path)


@router.post("/chat/threads/{thread_id}/messages")
async def send_message(request: Request, thread_id: int, body: _SendMessageRequest):
    chat_service: ChatService = request.app.state.chat_service

    if not chat_service.repository.is_chat_thread(thread_id):
        title_source = body.content or (body.attachments[0].name if body.attachments else "New chat")
        title = title_source[:100] if len(title_source) <= 100 else title_source[:97] + "..."
        await chat_service.repository.save_thread(thread_id, title)

    saved = await chat_service.save_attachments(thread_id, [a.model_dump() for a in body.attachments or []])

    metadata: dict = {}
    if body.reaction:
        metadata["reaction"] = body.reaction
    if saved:
        metadata["attachments"] = [
            {"name": s["name"], "content_type": s["content_type"], "file": Path(s["path"]).name} for s in saved
        ]
    await chat_service.repository.save_message(thread_id, "user", "user", body.content, metadata or None)

    images = [
        TaskImage(path=s["path"], content_type=s["content_type"])
        for s in saved
        if s["content_type"] in VISION_MIME_TYPES
    ]
    other_files = [s for s in saved if s["content_type"] not in VISION_MIME_TYPES]

    task = body.content
    notes = []
    if images:
        names = ", ".join(Path(s["path"]).name for s in saved if s["content_type"] in VISION_MIME_TYPES)
        notes.append(f"The user attached the following image(s), shown inline above: {names}.")
    if other_files:
        files = "\n".join(f"- {s['path']}" for s in other_files)
        notes.append(f"The user attached the following file(s). Use the read_file tool to view them:\n{files}")
    if notes:
        prefix = f"{body.content}\n\n" if body.content else ""
        task = prefix + "\n\n".join(notes)

    await pubsub.publish(TaskRequest(task=task, thread_id=thread_id, images=images))

    return {"ok": True}


@router.post("/chat/threads/{thread_id}/stop")
async def stop_task(request: Request, thread_id: int):
    await pubsub.publish(StopTaskRequest(thread_id=thread_id))
    return {"ok": True}


@router.get("/chat/threads/{thread_id}/events")
async def thread_events(request: Request, thread_id: int):
    chat_service: ChatService = request.app.state.chat_service
    event_bus = chat_service.event_bus

    async def _event_stream():
        queue = event_bus.subscribe(thread_id)
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    event_type = event.get("type", "message")
                    data = json.dumps(event, default=_serialize)
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        except GeneratorExit:
            pass
        finally:
            event_bus.unsubscribe(thread_id, queue)
            logger.debug(f"SSE client disconnected from thread {thread_id}")

    return StreamingResponse(_event_stream(), media_type="text/event-stream")
