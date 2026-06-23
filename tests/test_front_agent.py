import os
from pathlib import Path

import asyncpg
import pytest

from synthia.agents.agent import DEFAULT_MODEL, Agent, required_api_key
from synthia.migrations.runner import run_migrations
from synthia.service.task_repository import TaskRepository

_TASK_KEY = required_api_key(DEFAULT_MODEL)
_HAS_KEYS = bool(_TASK_KEY and os.getenv(_TASK_KEY))


@pytest.fixture
async def repo(pgvector_container: str):
    run_migrations(pgvector_container)
    pool = await asyncpg.create_pool(pgvector_container, min_size=1, max_size=2)
    await pool.execute("DELETE FROM tasks")
    try:
        yield TaskRepository(pool)
    finally:
        await pool.close()


async def test_recent_returns_finished_tasks_newest_first(repo: TaskRepository) -> None:
    await repo.start(task_id="t1", thread_id=1, label="ottoman", request="download the doc", background=False)
    await repo.finish(task_id="t1", success=True, result="Saved 3 files.")
    await repo.start(task_id="t2", thread_id=2, label="kavita", request="rate my library", background=False)
    await repo.finish(task_id="t2", success=True, result="Rated 120 books.")

    rows = await repo.recent(limit=10)

    assert [r["id"] for r in rows] == ["t2", "t1"]
    assert rows[0]["request"] == "rate my library"
    assert rows[0]["result"] == "Rated 120 books."


async def test_recent_excludes_unfinished_tasks(repo: TaskRepository) -> None:
    await repo.start(task_id="running", thread_id=1, label="bg", request="long job", background=True)
    await repo.start(task_id="done", thread_id=1, label="quick", request="quick job", background=False)
    await repo.finish(task_id="done", success=True, result="done!")

    rows = await repo.recent(limit=10)

    assert [r["id"] for r in rows] == ["done"]


async def test_recent_excludes_errored_tasks(repo: TaskRepository) -> None:
    await repo.start(task_id="bad", thread_id=1, label="bad", request="boom", background=False)
    await repo.finish(task_id="bad", success=False, result="exploded")

    assert await repo.recent(limit=10) == []


async def test_for_thread_lists_all_statuses_for_thread(repo: TaskRepository) -> None:
    await repo.start(task_id="a", thread_id=1, label="a", request="ra", background=False)
    await repo.finish(task_id="a", success=True, result="done a")
    await repo.start(task_id="b", thread_id=1, label="b", request="rb", background=True)
    await repo.start(task_id="c", thread_id=2, label="c", request="rc", background=False)

    rows = await repo.for_thread(1)

    ids = {r["id"] for r in rows}
    assert ids == {"a", "b"}
    statuses = {r["id"]: r["status"] for r in rows}
    assert statuses["a"] == "done"
    assert statuses["b"] == "queued"


async def test_resume_keeps_same_row(repo: TaskRepository) -> None:
    await repo.start(task_id="t1", thread_id=1, label="first", request="step one", background=False)
    await repo.finish(task_id="t1", success=True, result="one done")
    await repo.start(task_id="t1", thread_id=1, label="", request="step two", background=False)
    await repo.finish(task_id="t1", success=True, result="two done")

    rows = await repo.recent(limit=10)

    assert len(rows) == 1
    assert rows[0]["request"] == "step two"
    assert rows[0]["result"] == "two done"
    assert rows[0]["label"] == "first"


async def test_search_filters_by_query_across_fields(repo: TaskRepository) -> None:
    await repo.start(task_id="t1", thread_id=1, label="magazines", request="check magazines", background=False)
    await repo.finish(task_id="t1", success=True, result="Atlantic is current")
    await repo.start(task_id="t2", thread_id=1, label="vacuum", request="compare robot vacuums", background=False)
    await repo.finish(task_id="t2", success=True, result="Roborock wins")

    assert [t["id"] for t in await repo.search("magazine")] == ["t1"]
    assert [t["id"] for t in await repo.search("Roborock")] == ["t2"]
    assert {t["id"] for t in await repo.search("")} == {"t1", "t2"}


@pytest.mark.skipif(not _HAS_KEYS, reason=f"requires {_TASK_KEY}")
async def test_explicit_session_id_resumes_context() -> None:
    agent = await Agent.create(cwd=Path(__file__).parent)
    try:
        first = await agent.run_for_result(
            objective="Remember: the codeword is BANANA. Just confirm.",
            session_id="task-resume-test",
        )
        assert first is not None and first.success

        second = await agent.run_for_result(
            objective="What is the codeword? Answer with just the word.",
            session_id="task-resume-test",
        )
        assert second is not None and second.success
        assert "BANANA" in second.result.upper()
    finally:
        await agent.disconnect()
