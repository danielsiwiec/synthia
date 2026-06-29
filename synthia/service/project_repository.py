from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from loguru import logger

VALID_STATUSES = ("active", "closed")

_COLUMNS = "id, name, status, document, next_step, sections, media, created_at, updated_at"


def _project(row: asyncpg.Record) -> dict[str, Any]:
    project = dict(row)
    project["sections"] = json.loads(project["sections"]) if project.get("sections") else []
    project["media"] = json.loads(project["media"]) if project.get("media") else []
    return project


def _row_to_project(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return _project(row) if row is not None else None


class ProjectRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create(
        self, *, name: str, document: str = "", status: str = "active", next_step: str = ""
    ) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            f"""
            INSERT INTO projects (name, status, document, next_step)
            VALUES ($1, $2, $3, $4)
            RETURNING {_COLUMNS}
            """,
            name,
            status,
            document,
            next_step,
        )
        return _project(row)

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
            f"""
            UPDATE projects
            SET name = COALESCE($2, name),
                status = COALESCE($3, status),
                document = COALESCE($4, document),
                next_step = COALESCE($5, next_step),
                updated_at = NOW()
            WHERE id = $1
            RETURNING {_COLUMNS}
            """,
            project_id,
            name,
            status,
            document,
            next_step,
        )
        return _row_to_project(row)

    async def get(self, project_id: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(f"SELECT {_COLUMNS} FROM projects WHERE id = $1", project_id)
        return _row_to_project(row)

    async def list_all(self) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(f"SELECT {_COLUMNS} FROM projects ORDER BY created_at DESC")
        return [_project(row) for row in rows]

    async def delete(self, project_id: str) -> bool:
        result = await self._pool.execute("DELETE FROM projects WHERE id = $1", project_id)
        deleted = result.endswith("1")
        if not deleted:
            logger.warning(f"Project {project_id} not found for deletion")
        return deleted

    async def add_section(self, project_id: str, title: str, body: str) -> dict[str, Any] | None:
        project = await self.get(project_id)
        if project is None:
            return None
        sections = project["sections"]
        order = max((s.get("order", 0) for s in sections), default=-1) + 1
        sections.append({"id": uuid.uuid4().hex, "title": title, "body": body, "order": order})
        return await self._write_sections(project_id, sections)

    async def update_section(
        self, project_id: str, section_id: str, title: str | None, body: str | None
    ) -> dict[str, Any] | None:
        project = await self.get(project_id)
        if project is None:
            return None
        sections = project["sections"]
        target = next((s for s in sections if s["id"] == section_id), None)
        if target is None:
            return None
        if title is not None:
            target["title"] = title
        if body is not None:
            target["body"] = body
        return await self._write_sections(project_id, sections)

    async def reorder_sections(self, project_id: str, section_ids: list[str]) -> dict[str, Any] | None:
        project = await self.get(project_id)
        if project is None:
            return None
        by_id = {s["id"]: s for s in project["sections"]}
        if set(section_ids) != set(by_id):
            return None
        sections = [{**by_id[sid], "order": i} for i, sid in enumerate(section_ids)]
        return await self._write_sections(project_id, sections)

    async def add_media(
        self, project_id: str, name: str, content_type: str, file: str, caption: str
    ) -> dict[str, Any] | None:
        project = await self.get(project_id)
        if project is None:
            return None
        media = project["media"]
        order = max((m.get("order", 0) for m in media), default=-1) + 1
        media.append(
            {
                "id": uuid.uuid4().hex,
                "name": name,
                "content_type": content_type,
                "file": file,
                "caption": caption,
                "order": order,
            }
        )
        row = await self._pool.fetchrow(
            f"UPDATE projects SET media = $2, updated_at = NOW() WHERE id = $1 RETURNING {_COLUMNS}",
            project_id,
            json.dumps(media),
        )
        return _row_to_project(row)

    async def _write_sections(self, project_id: str, sections: list[dict[str, Any]]) -> dict[str, Any] | None:
        sections = sorted(sections, key=lambda s: s.get("order", 0))
        row = await self._pool.fetchrow(
            f"UPDATE projects SET sections = $2, updated_at = NOW() WHERE id = $1 RETURNING {_COLUMNS}",
            project_id,
            json.dumps(sections),
        )
        return _row_to_project(row)
