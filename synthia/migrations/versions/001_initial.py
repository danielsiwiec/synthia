"""Initial migration with thread_sessions and conversations tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIMENSIONS = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS thread_sessions (
            thread_id BIGINT PRIMARY KEY,
            session_id TEXT NOT NULL
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transcript TEXT NOT NULL,
            summary TEXT NOT NULL,
            embedding vector({_EMBEDDING_DIMENSIONS}),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS conversations_embedding_idx
        ON conversations
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS conversations_created_at_idx
        ON conversations (created_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS conversations_fts_idx
        ON conversations
        USING gin(to_tsvector('english', summary || ' ' || transcript))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS conversations_fts_idx")
    op.execute("DROP INDEX IF EXISTS conversations_created_at_idx")
    op.execute("DROP INDEX IF EXISTS conversations_embedding_idx")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS thread_sessions")
