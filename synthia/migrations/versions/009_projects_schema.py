"""Convert a legacy projects table (objective/tldr/progress) to name/document

Revision ID: 009_projects_schema
Revises: 008_projects
Create Date: 2026-06-21

"""

from collections.abc import Sequence

from alembic import op

revision: str = "009_projects_schema"
down_revision: str | None = "008_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'objective'
            ) THEN
                ALTER TABLE projects ADD COLUMN IF NOT EXISTS name TEXT;
                ALTER TABLE projects ADD COLUMN IF NOT EXISTS document TEXT;

                UPDATE projects
                SET name = COALESCE(NULLIF(objective, ''), 'Untitled project')
                WHERE name IS NULL;

                UPDATE projects
                SET document = TRIM(BOTH E'\n' FROM
                    COALESCE(tldr, '')
                    || CASE WHEN COALESCE(progress, '') <> ''
                            THEN E'\n\n## Progress\n' || progress
                            ELSE '' END)
                WHERE document IS NULL;

                UPDATE projects SET document = '' WHERE document IS NULL;

                ALTER TABLE projects ALTER COLUMN name SET NOT NULL;
                ALTER TABLE projects ALTER COLUMN document SET DEFAULT '';
                ALTER TABLE projects ALTER COLUMN document SET NOT NULL;
                ALTER TABLE projects ALTER COLUMN status SET DEFAULT 'active';

                ALTER TABLE projects DROP COLUMN IF EXISTS objective;
                ALTER TABLE projects DROP COLUMN IF EXISTS tldr;
                ALTER TABLE projects DROP COLUMN IF EXISTS progress;
                ALTER TABLE projects DROP COLUMN IF EXISTS thread_id;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    pass
