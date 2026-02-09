"""Add push_subscriptions table for Web Push notifications

Revision ID: 004_push_subscriptions
Revises: 003_chat
Create Date: 2025-02-08

"""

from collections.abc import Sequence

from alembic import op

revision: str = "004_push_subscriptions"
down_revision: str | None = "003_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint TEXT PRIMARY KEY,
            keys_p256dh TEXT NOT NULL,
            keys_auth TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
