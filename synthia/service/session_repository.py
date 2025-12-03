import psycopg
from loguru import logger


class SessionRepository:
    def __init__(self, postgres_url: str):
        self._conn_string = postgres_url
        self._sessions: dict[int, str] = {}

    async def initialize(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._conn_string) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS thread_sessions (
                    thread_id BIGINT PRIMARY KEY,
                    session_id TEXT NOT NULL
                )
            """)
            await conn.commit()

            async with conn.cursor() as cur:
                await cur.execute("SELECT thread_id, session_id FROM thread_sessions")
                rows = await cur.fetchall()
                for thread_id, session_id in rows:
                    self._sessions[thread_id] = session_id

        logger.info(f"Loaded {len(self._sessions)} sessions from database")

    def get(self, thread_id: int) -> str | None:
        return self._sessions.get(thread_id)

    async def save(self, thread_id: int, session_id: str) -> None:
        self._sessions[thread_id] = session_id
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
