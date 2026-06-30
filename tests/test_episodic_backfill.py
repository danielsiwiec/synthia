from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from synthia.agents.episodic.backfill import _first_prompt, _pick_thread, apply_backfill, plan_backfill
from synthia.migrations.runner import run_migrations
from synthia.service.chat import ChatService


@pytest.fixture
async def pool(pgvector_container: str):
    run_migrations(pgvector_container)
    p = await asyncpg.create_pool(pgvector_container, min_size=1, max_size=2)
    await p.execute("DELETE FROM messages")
    await p.execute("DELETE FROM threads")
    await p.execute("DELETE FROM conversations")
    try:
        yield p
    finally:
        await p.close()


async def _add_conversation(pool: asyncpg.Pool, transcript: str, created_at: datetime) -> str:
    row = await pool.fetchrow(
        "INSERT INTO conversations (transcript, summary, created_at) VALUES ($1, '', $2) RETURNING id",
        transcript,
        created_at,
    )
    return str(row["id"])


def test_first_prompt_strips_user_prefix() -> None:
    assert _first_prompt("User: hello world\nThinking: ...") == "hello world"
    assert _first_prompt("User:no space") == "no space"


def test_pick_thread_prefers_closest_at_or_before() -> None:
    now = datetime(2026, 6, 9, 23, 0, tzinfo=UTC)
    candidates = [
        {"thread_id": 1, "last_message_at": now - timedelta(hours=2)},
        {"thread_id": 2, "last_message_at": now - timedelta(minutes=5)},
        {"thread_id": 3, "last_message_at": now + timedelta(hours=1)},
    ]
    assert _pick_thread(candidates, now) == 2


@pytest.mark.smoke
async def test_plan_backfill_matches_attachment_thread(pool: asyncpg.Pool, tmp_path) -> None:
    chat = ChatService(pool, cwd=tmp_path)
    await chat.initialize()
    await chat.repository.save_thread(1781046427742, "ticket")
    await chat.repository.save_message(
        1781046427742,
        "user",
        "user",
        "address my ticket",
        {"attachments": [{"file": "IMG.jpeg", "name": "IMG.jpeg", "content_type": "image/jpeg"}]},
    )
    conv_id = await _add_conversation(pool, "User: address my ticket\nResult: ok", datetime.now(tz=UTC))

    plan = await plan_backfill(pool)

    assert len(plan) == 1
    assert plan[0]["conversation_id"] == conv_id or str(plan[0]["conversation_id"]) == conv_id
    assert plan[0]["thread_id"] == 1781046427742


@pytest.mark.smoke
async def test_plan_skips_threads_without_attachments(pool: asyncpg.Pool) -> None:
    chat = ChatService(pool)
    await chat.initialize()
    await chat.repository.save_thread(500, "plain")
    await chat.repository.save_message(500, "user", "user", "no files here", None)
    await _add_conversation(pool, "User: no files here\nResult: ok", datetime.now(tz=UTC))

    assert await plan_backfill(pool, attachments_only=True) == []


@pytest.mark.smoke
async def test_apply_backfill_sets_thread_id(pool: asyncpg.Pool, tmp_path) -> None:
    chat = ChatService(pool, cwd=tmp_path)
    await chat.initialize()
    await chat.repository.save_thread(900, "t")
    await chat.repository.save_message(
        900, "user", "user", "look", {"attachments": [{"file": "a.png", "name": "a.png", "content_type": "image/png"}]}
    )
    conv_id = await _add_conversation(pool, "User: look\nResult: ok", datetime.now(tz=UTC))

    plan = await plan_backfill(pool)
    applied = await apply_backfill(pool, plan)

    assert applied == 1
    stored = await pool.fetchval("SELECT thread_id FROM conversations WHERE id = $1::uuid", conv_id)
    assert stored == 900
