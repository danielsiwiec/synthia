"""Migrate mem0 embeddings from OpenAI (1536d) to Ollama nomic-embed-text (768d)

Backs up the mem0 table, drops it, then re-ingests all memories
using mem0's API with the new embedding configuration.

Revision ID: 005_migrate_mem0_embeddings
Revises: 004_push_subscriptions
Create Date: 2026-02-08

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from loguru import logger

revision: str = "005_migrate_mem0_embeddings"
down_revision: str | None = "004_push_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    has_table = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'mem0')")
    ).scalar()
    if not has_table:
        return

    ollama_url = os.environ.get("OLLAMA_URL")
    if not ollama_url:
        return

    rows = conn.execute(sa.text("SELECT id, payload FROM mem0 ORDER BY id")).fetchall()
    if not rows:
        return

    memories = []
    for row in rows:
        payload = row[1]
        if isinstance(payload, dict):
            memories.append({"data": payload.get("data", ""), "user_id": payload.get("user_id", "default")})

    conn.execute(sa.text("CREATE TABLE mem0_backup AS SELECT * FROM mem0"))
    conn.execute(sa.text("DROP TABLE mem0"))

    conn.execute(sa.text("COMMIT"))

    from mem0 import Memory

    from synthia.agents.memory.client import OLLAMA_EMBEDDING_DIMS, OLLAMA_EMBEDDING_MODEL

    mem0_config = {
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": OLLAMA_EMBEDDING_MODEL,
                "ollama_base_url": ollama_url,
            },
        },
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": os.environ["POSTGRES_CONNECTION_STRING"],
                "embedding_model_dims": OLLAMA_EMBEDDING_DIMS,
            },
        },
    }
    memory_client = Memory.from_config(mem0_config)

    logger.info(f"Re-ingesting {len(memories)} memories with new embeddings...")
    for mem in memories:
        if mem["data"]:
            memory_client.add(mem["data"], user_id=mem["user_id"], infer=False)
    logger.info("Memory re-ingestion complete")

    conn.execute(sa.text("BEGIN"))


def downgrade() -> None:
    conn = op.get_bind()

    has_backup = conn.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'mem0_backup')")
    ).scalar()

    if has_backup:
        conn.execute(sa.text("DROP TABLE IF EXISTS mem0"))
        conn.execute(sa.text("ALTER TABLE mem0_backup RENAME TO mem0"))
