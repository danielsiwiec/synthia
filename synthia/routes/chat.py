import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel

from synthia.helpers.pubsub import pubsub
from synthia.service.chat import ChatService
from synthia.service.models import StopTaskRequest, TaskRequest

router = APIRouter()

_static_dir = Path(__file__).parent.parent / "static"


class _SendMessageRequest(BaseModel):
    content: str


def _serialize(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "hex"):
        return str(obj)
    return obj


@router.get("/chat")
async def chat_ui():
    return FileResponse(_static_dir / "chat.html", headers={"Cache-Control": "no-cache"})


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


@router.delete("/chat/threads/{thread_id}")
async def delete_thread(request: Request, thread_id: int):
    chat_service: ChatService = request.app.state.chat_service
    await chat_service.repository.delete_thread(thread_id)
    return {"ok": True}


@router.get("/chat/threads/{thread_id}/messages")
async def get_messages(request: Request, thread_id: int):
    chat_service: ChatService = request.app.state.chat_service
    messages = await chat_service.repository.get_messages(thread_id)
    return [
        {
            "id": str(m["id"]),
            "thread_id": str(m["thread_id"]),
            "role": m["role"],
            "message_type": m["message_type"],
            "content": m["content"],
            "metadata": json.loads(m["metadata"]) if m["metadata"] else None,
            "created_at": m["created_at"].isoformat() if m["created_at"] else None,
        }
        for m in messages
    ]


@router.post("/chat/threads/{thread_id}/messages")
async def send_message(request: Request, thread_id: int, body: _SendMessageRequest):
    chat_service: ChatService = request.app.state.chat_service

    if not chat_service.repository.is_chat_thread(thread_id):
        title = body.content[:100] if len(body.content) <= 100 else body.content[:97] + "..."
        await chat_service.repository.save_thread(thread_id, title)

    await chat_service.repository.save_message(thread_id, "user", "user", body.content)

    await pubsub.publish(TaskRequest(task=body.content, thread_id=thread_id))

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
