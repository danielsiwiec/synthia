"""Add ordered sections and media attachments to projects

Revision ID: 012_project_sections_media
Revises: 011_thread_project_link
Create Date: 2026-06-29

"""

from collections.abc import Sequence

from alembic import op

revision: str = "012_project_sections_media"
down_revision: str | None = "011_thread_project_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS sections JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS media JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS media")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS sections")
