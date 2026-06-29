"""Record the source thread id on episodic conversations

Revision ID: 013_conversation_thread_id
Revises: 012_project_sections_media
Create Date: 2026-06-29

"""

from collections.abc import Sequence

from alembic import op

revision: str = "013_conversation_thread_id"
down_revision: str | None = "012_project_sections_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS thread_id BIGINT")


def downgrade() -> None:
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS thread_id")
