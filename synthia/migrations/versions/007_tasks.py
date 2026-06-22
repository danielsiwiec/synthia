"""Tasks table — task-agent executions delegated by the front agent

Revision ID: 007_tasks
Revises: 006_job_executions
Create Date: 2026-06-21

"""

from collections.abc import Sequence

from alembic import op

revision: str = "007_tasks"
down_revision: str | None = "006_job_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            thread_id BIGINT,
            label TEXT,
            request TEXT,
            result TEXT,
            status TEXT NOT NULL,
            background BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS tasks_updated_at_idx ON tasks (updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS tasks_thread_id_idx ON tasks (thread_id, updated_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS tasks_thread_id_idx")
    op.execute("DROP INDEX IF EXISTS tasks_updated_at_idx")
    op.execute("DROP TABLE IF EXISTS tasks")
