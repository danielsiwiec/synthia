from __future__ import annotations

import re
from typing import Any

import asyncpg

_USER_PREFIX = re.compile(r"^User:\s?")


def _first_prompt(transcript: str) -> str:
    first_line = transcript.split("\n", 1)[0]
    return _USER_PREFIX.sub("", first_line).strip()


async def _threads_with_attachments(conn: asyncpg.Pool | asyncpg.Connection) -> set[int]:
    rows = await conn.fetch(
        "SELECT DISTINCT thread_id FROM messages WHERE metadata IS NOT NULL AND metadata::text ILIKE '%attachment%'"
    )
    return {row["thread_id"] for row in rows}


async def _candidate_threads(conn: asyncpg.Pool | asyncpg.Connection, first_prompt: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT thread_id, MAX(created_at) AS last_message_at
        FROM messages
        WHERE role = 'user' AND content = $1
        GROUP BY thread_id
        """,
        first_prompt,
    )
    return [dict(row) for row in rows]


def _pick_thread(candidates: list[dict[str, Any]], conversation_created_at: Any) -> int | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["thread_id"]
    at_or_before = [c for c in candidates if c["last_message_at"] <= conversation_created_at]
    pool = at_or_before or candidates
    best = min(pool, key=lambda c: abs((conversation_created_at - c["last_message_at"]).total_seconds()))
    return best["thread_id"]


async def plan_backfill(conn: asyncpg.Pool | asyncpg.Connection, attachments_only: bool = True) -> list[dict[str, Any]]:
    conversations = await conn.fetch(
        "SELECT id, transcript, created_at FROM conversations WHERE thread_id IS NULL ORDER BY created_at"
    )
    attachment_threads = await _threads_with_attachments(conn) if attachments_only else None

    plan: list[dict[str, Any]] = []
    for conversation in conversations:
        first_prompt = _first_prompt(conversation["transcript"])
        if not first_prompt:
            continue
        candidates = await _candidate_threads(conn, first_prompt)
        if attachment_threads is not None:
            candidates = [c for c in candidates if c["thread_id"] in attachment_threads]
        thread_id = _pick_thread(candidates, conversation["created_at"])
        if thread_id is None:
            continue
        plan.append(
            {
                "conversation_id": conversation["id"],
                "thread_id": thread_id,
                "ambiguous": len(candidates) > 1,
                "first_prompt": first_prompt[:80],
            }
        )
    return plan


async def apply_backfill(conn: asyncpg.Pool | asyncpg.Connection, plan: list[dict[str, Any]]) -> int:
    count = 0
    for entry in plan:
        await conn.execute(
            "UPDATE conversations SET thread_id = $1 WHERE id = $2 AND thread_id IS NULL",
            entry["thread_id"],
            entry["conversation_id"],
        )
        count += 1
    return count
