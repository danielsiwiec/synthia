from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import psycopg
from loguru import logger

if TYPE_CHECKING:
    from synthia.agents.agent import ClaudeAgent


class SessionRepository:
    def __init__(self, postgres_url: str):
        self._conn_string = postgres_url
        self._sessions: dict[int, str] = {}
        self._agents: dict[int, ClaudeAgent] = {}

    @classmethod
    async def create(cls, postgres_url: str) -> SessionRepository:
        repository = cls(postgres_url)
        await repository._initialize()
        return repository

    async def _initialize(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._conn_string) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT thread_id, session_id FROM thread_sessions")
                rows = await cur.fetchall()
                for thread_id, session_id in rows:
                    self._sessions[thread_id] = session_id

        logger.info(f"Loaded {len(self._sessions)} sessions from database")

    def get(self, thread_id: int) -> tuple[ClaudeAgent | None, str | None]:
        return self._agents.pop(thread_id, None), self._sessions.get(thread_id)

    def save(self, thread_id: int, session_id: str, agent: ClaudeAgent | None = None) -> None:
        self._sessions[thread_id] = session_id
        if agent and agent._client:
            self._agents[thread_id] = agent
        else:
            self._agents.pop(thread_id, None)
        asyncio.create_task(self._persist(thread_id, session_id))

    async def _persist(self, thread_id: int, session_id: str) -> None:
        async with await psycopg.AsyncConnection.connect(self._conn_string) as conn:
            await conn.execute(
                """
                INSERT INTO thread_sessions (thread_id, session_id)
                VALUES (%s, %s)
                ON CONFLICT (thread_id) DO UPDATE SET session_id = EXCLUDED.session_id
                """,
                (thread_id, session_id),
            )
            await conn.commit()
