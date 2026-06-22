from __future__ import annotations

from typing import Any

import asyncpg
from loguru import logger


class TaskRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def start(self, *, task_id: str, thread_id: int | None, label: str, request: str, background: bool) -> None:
        try:
            await self._pool.execute(
                """
                INSERT INTO tasks (id, thread_id, label, request, status, background)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    label = COALESCE(NULLIF(EXCLUDED.label, ''), tasks.label),
                    request = EXCLUDED.request,
                    updated_at = NOW()
                """,
                task_id,
                thread_id,
                label,
                request,
                "queued" if background else "running",
                background,
            )
        except Exception as error:
            logger.error(f"Failed to start task record: {error}")

    async def set_status(self, task_id: str, status: str) -> None:
        try:
            await self._pool.execute("UPDATE tasks SET status = $2, updated_at = NOW() WHERE id = $1", task_id, status)
        except Exception as error:
            logger.error(f"Failed to update task status: {error}")

    async def finish(self, *, task_id: str, success: bool, result: str | None) -> None:
        try:
            await self._pool.execute(
                "UPDATE tasks SET status = $2, result = $3, updated_at = NOW() WHERE id = $1",
                task_id,
                "done" if success else "error",
                result,
            )
        except Exception as error:
            logger.error(f"Failed to finish task record: {error}")

    async def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, thread_id, label, request, result, status, updated_at
            FROM tasks
            WHERE status = 'done'
            ORDER BY updated_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]

    async def search(self, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, thread_id, label, request, result, status, updated_at
            FROM tasks
            WHERE ($1 = '' OR label ILIKE '%' || $1 || '%' OR request ILIKE '%' || $1 || '%'
                   OR result ILIKE '%' || $1 || '%')
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            query,
            limit,
        )
        return [dict(row) for row in rows]

    async def for_thread(self, thread_id: int, limit: int = 20) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, thread_id, label, request, result, status, updated_at
            FROM tasks
            WHERE thread_id = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            thread_id,
            limit,
        )
        return [dict(row) for row in rows]
