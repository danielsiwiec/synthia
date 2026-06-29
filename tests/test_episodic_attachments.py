import json

import asyncpg
import pytest

from synthia.agents.episodic.attachments import attachments_for_thread, render_attachments_block
from synthia.agents.episodic.tools.show import create_show_tool
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


@pytest.mark.smoke
async def test_attachments_for_thread_builds_paths(pool: asyncpg.Pool, tmp_path) -> None:
    chat = ChatService(pool, cwd=tmp_path)
    await chat.initialize()
    await chat.repository.save_thread(1781046427742, "thread")
    metadata = {"attachments": [{"file": "IMG_6207.jpeg", "name": "ticket.jpeg", "content_type": "image/jpeg"}]}
    await chat.repository.save_message(1781046427742, "user", "user", "ticket", metadata)

    found = await attachments_for_thread(pool, tmp_path, 1781046427742)

    paths = [a["path"] for a in found]
    assert str(tmp_path / "uploads" / "1781046427742" / "IMG_6207.jpeg") in paths
    assert any(a["name"] == "ticket.jpeg" and a["content_type"] == "image/jpeg" for a in found)


@pytest.mark.smoke
async def test_render_attachments_block_empty() -> None:
    assert render_attachments_block([]) == ""


@pytest.mark.smoke
async def test_episodic_show_includes_attachment_paths(pool: asyncpg.Pool, tmp_path) -> None:
    thread_id = 222333
    chat = ChatService(pool, cwd=tmp_path)
    await chat.initialize()
    await chat.repository.save_thread(thread_id, "thread")
    metadata = {"attachments": [{"file": "shot.png", "name": "shot.png", "content_type": "image/png"}]}
    await chat.repository.save_message(thread_id, "user", "user", "a shot", metadata)
    row = await pool.fetchrow(
        """
        INSERT INTO conversations (transcript, summary, embedding, thread_id)
        VALUES ('t', 's', $1::vector, $2)
        RETURNING id
        """,
        json.dumps([0.0] * 384),
        thread_id,
    )

    show = create_show_tool(pool, cwd=tmp_path)
    result = await show(str(row["id"]))

    assert "shot.png" in result
    assert str(tmp_path / "uploads" / str(thread_id) / "shot.png") in result


@pytest.mark.smoke
async def test_episodic_show_without_thread_id_has_no_attachments(pool: asyncpg.Pool, tmp_path) -> None:
    row = await pool.fetchrow(
        """
        INSERT INTO conversations (transcript, summary, embedding, thread_id)
        VALUES ('t', 's', $1::vector, NULL)
        RETURNING id
        """,
        json.dumps([0.0] * 384),
    )

    show = create_show_tool(pool, cwd=tmp_path)
    result = await show(str(row["id"]))

    assert "Attachments" not in result
