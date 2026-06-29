"""Link each project to a single owning thread

Revision ID: 011_thread_project_link
Revises: 010_project_next_step
Create Date: 2026-06-29

"""

from collections.abc import Sequence

from alembic import op

revision: str = "011_thread_project_link"
down_revision: str | None = "010_project_next_step"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_threads_project_id ON threads(project_id) WHERE project_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_threads_project_id")
    op.execute("ALTER TABLE threads DROP COLUMN IF EXISTS project_id")
