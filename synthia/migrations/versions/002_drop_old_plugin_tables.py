"""Drop tables from previous episodic-memory plugin

Revision ID: 002_drop_old_plugin_tables
Revises: 001_initial
Create Date: 2025-01-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "002_drop_old_plugin_tables"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vec_exchanges")
    op.execute("DROP TABLE IF EXISTS tool_calls")
    op.execute("DROP TABLE IF EXISTS exchanges")


def downgrade() -> None:
    pass
