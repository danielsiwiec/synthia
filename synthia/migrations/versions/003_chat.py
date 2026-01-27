"""Add threads and messages tables for chat UI

Revision ID: 003_chat
Revises: 002_drop_old_plugin_tables
Create Date: 2025-01-26

"""

from collections.abc import Sequence

from alembic import op

revision: str = "003_chat"
down_revision: str | None = "002_drop_old_plugin_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id BIGINT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id BIGINT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS messages_thread_id_created_at_idx
        ON messages (thread_id, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS messages_thread_id_created_at_idx")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS threads")
