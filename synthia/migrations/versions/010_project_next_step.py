"""Add a next_step field to projects and backfill existing rows

Revision ID: 010_project_next_step
Revises: 009_projects_schema
Create Date: 2026-06-22

"""

from collections.abc import Sequence

from alembic import op

revision: str = "010_project_next_step"
down_revision: str | None = "009_projects_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS next_step TEXT NOT NULL DEFAULT ''")
    op.execute("UPDATE projects SET next_step = 'Define the next step for this project' WHERE next_step = ''")


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS next_step")
