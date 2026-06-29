from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import asyncpg


def _uploads_dir(cwd: str | Path | None) -> Path:
    return ((Path(cwd) if cwd else Path.cwd()) / "uploads").resolve()


async def attachments_for_thread(pool: asyncpg.Pool, cwd: str | Path | None, thread_id: int) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT metadata FROM messages WHERE thread_id = $1 AND metadata IS NOT NULL ORDER BY created_at ASC",
        thread_id,
    )
    base = _uploads_dir(cwd) / str(thread_id)
    found: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(row["metadata"]) if row["metadata"] else None
        if not metadata:
            continue
        for attachment in metadata.get("attachments", []) or []:
            file = attachment.get("file")
            if not file:
                continue
            found.append(
                {
                    "name": attachment.get("name", file),
                    "content_type": attachment.get("content_type", ""),
                    "path": str(base / file),
                }
            )
    return found


def render_attachments_block(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""
    lines = "\n".join(f"- {a['name']} ({a['content_type'] or 'unknown'}) — path: {a['path']}" for a in attachments)
    return (
        "\n\n**Attachments (files saved on disk; pass a path to a tool that takes a file path, "
        f"e.g. attach_project_media):**\n{lines}\n"
    )
