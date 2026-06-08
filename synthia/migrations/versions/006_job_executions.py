"""Job executions ledger for skill optimization

Revision ID: 006_job_executions
Revises: 005_migrate_mem0_embeddings
Create Date: 2026-06-04

"""

from collections.abc import Sequence

from alembic import op

revision: str = "006_job_executions"
down_revision: str | None = "005_migrate_mem0_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS job_executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_name TEXT,
            skill_names TEXT[] NOT NULL DEFAULT '{}',
            thread_id BIGINT,
            success BOOLEAN NOT NULL,
            error TEXT,
            cost_usd NUMERIC,
            duration_s NUMERIC,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            skill_versions JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS job_executions_job_name_idx
        ON job_executions (job_name, created_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS job_executions_skill_names_idx
        ON job_executions USING gin (skill_names)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS job_executions_created_at_idx
        ON job_executions (created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS job_executions_created_at_idx")
    op.execute("DROP INDEX IF EXISTS job_executions_skill_names_idx")
    op.execute("DROP INDEX IF EXISTS job_executions_job_name_idx")
    op.execute("DROP TABLE IF EXISTS job_executions")
