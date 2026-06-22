from __future__ import annotations

import json
from typing import Any

import asyncpg
from loguru import logger


class JobExecutionRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def record(
        self,
        *,
        job_name: str | None,
        skill_names: list[str],
        thread_id: int | None,
        success: bool,
        error: str | None = None,
        cost_usd: float | None = None,
        duration_s: float | None = None,
        tool_call_count: int = 0,
        skill_versions: dict[str, str] | None = None,
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO job_executions (
                        job_name, skill_names, thread_id, success, error,
                        cost_usd, duration_s, tool_call_count, skill_versions
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                    """,
                    job_name,
                    skill_names,
                    thread_id,
                    success,
                    error,
                    cost_usd,
                    duration_s,
                    tool_call_count,
                    json.dumps(skill_versions or {}),
                )
        except Exception as e:
            logger.error(f"Failed to record job execution: {e}")

    async def recent(self, limit: int = 10, query: str = "") -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, job_name, skill_names, thread_id, success, error, cost_usd, duration_s, created_at
                FROM job_executions
                WHERE ($2 = '' OR job_name ILIKE '%' || $2 || '%' OR error ILIKE '%' || $2 || '%')
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
                query,
            )
        return [dict(row) for row in rows]

    async def recent_for_skill(self, skill_name: str, days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, job_name, skill_names, thread_id, success, error,
                       cost_usd, duration_s, tool_call_count, skill_versions, created_at
                FROM job_executions
                WHERE $1 = ANY(skill_names)
                  AND created_at >= NOW() - make_interval(days => $2)
                ORDER BY created_at DESC
                LIMIT $3
                """,
                skill_name,
                days,
                limit,
            )
        return [dict(row) for row in rows]

    async def recent_for_job(self, job_name: str, days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, job_name, skill_names, thread_id, success, error,
                       cost_usd, duration_s, tool_call_count, skill_versions, created_at
                FROM job_executions
                WHERE job_name = $1
                  AND created_at >= NOW() - make_interval(days => $2)
                ORDER BY created_at DESC
                LIMIT $3
                """,
                job_name,
                days,
                limit,
            )
        return [dict(row) for row in rows]

    async def skill_summary(self, days: int = 7) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT skill,
                       COUNT(*) AS runs,
                       COUNT(*) FILTER (WHERE NOT success) AS failures,
                       AVG(cost_usd) AS avg_cost_usd,
                       AVG(duration_s) AS avg_duration_s,
                       AVG(tool_call_count) AS avg_tool_calls
                FROM job_executions, unnest(skill_names) AS skill
                WHERE created_at >= NOW() - make_interval(days => $1)
                GROUP BY skill
                ORDER BY failures DESC, avg_cost_usd DESC NULLS LAST
                """,
                days,
            )
        return [dict(row) for row in rows]
