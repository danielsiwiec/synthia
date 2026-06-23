"""Projects table — user projects managed by the front agent

Revision ID: 008_projects
Revises: 007_tasks
Create Date: 2026-06-21

"""

from collections.abc import Sequence

from alembic import op

revision: str = "008_projects"
down_revision: str | None = "007_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            document TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS projects_status_idx ON projects (status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS projects_created_at_idx ON projects (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS projects_created_at_idx")
    op.execute("DROP INDEX IF EXISTS projects_status_idx")
    op.execute("DROP TABLE IF EXISTS projects")
