import asyncio
import base64
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import asyncpg
from loguru import logger

from synthia.agents.agent import InitMessage, Message, Result, Thought, ToolCall
from synthia.service.models import OutgoingImage, ProgressNotification


def _safe_filename(name: str) -> str:
    cleaned = name.replace("\\", "/").replace("\x00", "")
    return Path(cleaned).name or "attachment"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _attachment_path(uploads_dir: Path, thread_id: int, filename: str) -> Path | None:
    thread_dir = (uploads_dir / str(thread_id)).resolve()
    candidate = (thread_dir / _safe_filename(filename)).resolve()
    if candidate.parent != thread_dir:
        return None
    return candidate


async def _save_image_file(uploads_dir: Path, thread_id: int, src: Path, name: str) -> Path:
    thread_dir = uploads_dir / str(thread_id)
    thread_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(thread_dir / _safe_filename(name))
    data = await asyncio.to_thread(src.read_bytes)
    await asyncio.to_thread(dest.write_bytes, data)
    return dest


async def _save_attachments(
    uploads_dir: Path, thread_id: int, attachments: list[dict[str, Any]]
) -> list[dict[str, str]]:
    if not attachments:
        return []
    thread_dir = uploads_dir / str(thread_id)
    thread_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, str]] = []
    for attachment in attachments:
        raw = base64.b64decode(attachment["data"])
        dest = _unique_path(thread_dir / _safe_filename(attachment["name"]))
        await asyncio.to_thread(dest.write_bytes, raw)
        saved.append(
            {"name": attachment["name"], "content_type": attachment.get("content_type", ""), "path": str(dest)}
        )
    return saved


class ChatEventBus:
    def __init__(self):
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, thread_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[thread_id].add(queue)
        return queue

    def unsubscribe(self, thread_id: int, queue: asyncio.Queue):
        self._subscribers[thread_id].discard(queue)
        if not self._subscribers[thread_id]:
            del self._subscribers[thread_id]

    async def push(self, thread_id: int, event: dict):
        for queue in self._subscribers.get(thread_id, set()):
            await queue.put(event)


class MessageRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._chat_thread_ids: set[int] = set()

    async def initialize(self):
        rows = await self._pool.fetch("SELECT id FROM threads")
        self._chat_thread_ids = {row["id"] for row in rows}
        logger.info(f"Loaded {len(self._chat_thread_ids)} chat threads from database")

    def is_chat_thread(self, thread_id: int) -> bool:
        return thread_id in self._chat_thread_ids

    async def save_thread(self, thread_id: int, title: str):
        await self._pool.execute(
            """
            INSERT INTO threads (id, title)
            VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
            """,
            thread_id,
            title,
        )
        self._chat_thread_ids.add(thread_id)

    async def list_threads(self) -> list[dict[str, Any]]:
        rows = await self._pool.fetch("SELECT id, title, created_at, updated_at FROM threads ORDER BY updated_at DESC")
        return [dict(row) for row in rows]

    async def delete_thread(self, thread_id: int):
        await self._pool.execute("DELETE FROM threads WHERE id = $1", thread_id)
        self._chat_thread_ids.discard(thread_id)

    async def save_message(
        self, thread_id: int, role: str, message_type: str, content: str, metadata: dict | None = None
    ):
        await self._pool.execute(
            """
            INSERT INTO messages (thread_id, role, message_type, content, metadata)
            VALUES ($1, $2, $3, $4, $5)
            """,
            thread_id,
            role,
            message_type,
            content,
            json.dumps(metadata) if metadata else None,
        )
        await self._pool.execute("UPDATE threads SET updated_at = NOW() WHERE id = $1", thread_id)

    async def save_thought(self, thread_id: int, content: str):
        updated = await self._pool.fetchval(
            """
            UPDATE messages SET content = $2
            WHERE id = (
                SELECT id FROM messages WHERE thread_id = $1 ORDER BY created_at DESC, id DESC LIMIT 1
            ) AND message_type = 'thought'
            RETURNING id
            """,
            thread_id,
            content,
        )
        if updated is None:
            await self.save_message(thread_id, "assistant", "thought", content)
        else:
            await self._pool.execute("UPDATE threads SET updated_at = NOW() WHERE id = $1", thread_id)

    async def get_messages(self, thread_id: int) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, thread_id, role, message_type, content, metadata, created_at
            FROM messages
            WHERE thread_id = $1
            ORDER BY created_at ASC
            """,
            thread_id,
        )
        return [dict(row) for row in rows]


class ChatService:
    def __init__(self, pool: asyncpg.Pool, cwd: str | Path | None = None):
        self._event_bus = ChatEventBus()
        self._repository = MessageRepository(pool)
        self._uploads_dir = ((Path(cwd) if cwd else Path.cwd()) / "uploads").resolve()

    async def initialize(self):
        await self._repository.initialize()

    @property
    def event_bus(self) -> ChatEventBus:
        return self._event_bus

    @property
    def repository(self) -> MessageRepository:
        return self._repository

    async def save_attachments(self, thread_id: int, attachments: list[dict[str, Any]]) -> list[dict[str, str]]:
        return await _save_attachments(self._uploads_dir, thread_id, attachments)

    def attachment_path(self, thread_id: int, filename: str) -> Path | None:
        return _attachment_path(self._uploads_dir, thread_id, filename)

    async def handle_message(self, message: Message):
        thread_id = message.thread_id
        if thread_id is None:
            return

        if isinstance(message, InitMessage):
            await self._event_bus.push(
                thread_id, {"type": "init", "session_id": message.session_id, "prompt": message.prompt}
            )
            return

        if isinstance(message, Thought):
            thinking = message.thinking.strip()
            await self._event_bus.push(thread_id, {"type": "thought", "thinking": thinking})
            if self._repository.is_chat_thread(thread_id):
                await self._repository.save_thought(thread_id, thinking)
            return

        if isinstance(message, ToolCall):
            return

        if isinstance(message, Result):
            event = {
                "type": "result",
                "success": message.success,
                "result": message.result,
                "error": message.error,
                "cost_usd": message.cost_usd,
            }
            await self._event_bus.push(thread_id, event)

            if self._repository.is_chat_thread(thread_id):
                await self._repository.save_message(
                    thread_id,
                    "assistant",
                    "result",
                    message.result,
                    {"cost_usd": message.cost_usd, "success": message.success},
                )

    async def handle_progress(self, notification: ProgressNotification):
        if notification.thread_id is None:
            return
        await self._event_bus.push(notification.thread_id, {"type": "progress", "summary": notification.summary})

    async def handle_image(self, image: OutgoingImage):
        thread_id = image.thread_id
        if not self._repository.is_chat_thread(thread_id):
            return
        src = Path(image.source_path)
        if not src.is_file():
            logger.warning(f"send_image: source file missing: {src}")
            return
        dest = await _save_image_file(self._uploads_dir, thread_id, src, image.name)
        file = dest.name
        attachment = {"name": image.name, "content_type": image.content_type, "file": file}
        await self._repository.save_message(
            thread_id, "assistant", "image", image.caption, {"attachments": [attachment]}
        )
        url = f"/chat/threads/{thread_id}/attachments/{file}"
        await self._event_bus.push(
            thread_id,
            {
                "type": "image",
                "caption": image.caption,
                "attachment": {"type": "image", "name": image.name, "content_type": image.content_type, "url": url},
            },
        )
