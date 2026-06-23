from __future__ import annotations

from typing import Any

import asyncpg
from loguru import logger

VALID_STATUSES = ("active", "closed")


class ProjectRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create(
        self, *, name: str, document: str = "", status: str = "active", next_step: str = ""
    ) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            """
            INSERT INTO projects (name, status, document, next_step)
            VALUES ($1, $2, $3, $4)
            RETURNING id, name, status, document, next_step, created_at, updated_at
            """,
            name,
            status,
            document,
            next_step,
        )
        return dict(row)

    async def update(
        self,
        *,
        project_id: str,
        name: str | None = None,
        status: str | None = None,
        document: str | None = None,
        next_step: str | None = None,
    ) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            """
            UPDATE projects
            SET name = COALESCE($2, name),
                status = COALESCE($3, status),
                document = COALESCE($4, document),
                next_step = COALESCE($5, next_step),
                updated_at = NOW()
            WHERE id = $1
            RETURNING id, name, status, document, next_step, created_at, updated_at
            """,
            project_id,
            name,
            status,
            document,
            next_step,
        )
        return dict(row) if row else None

    async def get(self, project_id: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT id, name, status, document, next_step, created_at, updated_at FROM projects WHERE id = $1",
            project_id,
        )
        return dict(row) if row else None

    async def list_all(self) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, name, status, document, next_step, created_at, updated_at
            FROM projects
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in rows]

    async def delete(self, project_id: str) -> bool:
        result = await self._pool.execute("DELETE FROM projects WHERE id = $1", project_id)
        deleted = result.endswith("1")
        if not deleted:
            logger.warning(f"Project {project_id} not found for deletion")
        return deleted
