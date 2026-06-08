import asyncpg
import pytest

from synthia.migrations.runner import run_migrations
from synthia.service.job_execution_repository import JobExecutionRepository


@pytest.fixture
async def repo(pgvector_container: str):
    run_migrations(pgvector_container)
    pool = await asyncpg.create_pool(pgvector_container, min_size=1, max_size=2)
    await pool.execute("DELETE FROM job_executions")
    try:
        yield JobExecutionRepository(pool)
    finally:
        await pool.close()


async def test_record_and_query_by_skill(repo: JobExecutionRepository) -> None:
    await repo.record(
        job_name="magazine-check-daily",
        skill_names=["magazines"],
        thread_id=42,
        success=False,
        error="kavita 500",
        cost_usd=0.12,
        duration_s=31.5,
        tool_call_count=9,
        skill_versions={"magazines": "abc123"},
    )

    rows = await repo.recent_for_skill("magazines", days=1)
    assert len(rows) == 1
    row = rows[0]
    assert row["job_name"] == "magazine-check-daily"
    assert row["skill_names"] == ["magazines"]
    assert row["success"] is False
    assert row["error"] == "kavita 500"
    assert float(row["cost_usd"]) == pytest.approx(0.12)
    assert row["tool_call_count"] == 9

    assert await repo.recent_for_skill("other-skill", days=1) == []


async def test_skill_summary_ranks_failures_first(repo: JobExecutionRepository) -> None:
    for _ in range(3):
        await repo.record(
            job_name="j1",
            skill_names=["healthy"],
            thread_id=1,
            success=True,
            cost_usd=0.01,
            duration_s=2,
            tool_call_count=2,
        )
    await repo.record(
        job_name="j2",
        skill_names=["flaky"],
        thread_id=2,
        success=False,
        cost_usd=0.5,
        duration_s=40,
        tool_call_count=12,
    )

    summary = await repo.skill_summary(days=1)
    by_skill = {row["skill"]: row for row in summary}
    assert by_skill["flaky"]["failures"] == 1
    assert by_skill["healthy"]["failures"] == 0
    assert summary[0]["skill"] == "flaky"
