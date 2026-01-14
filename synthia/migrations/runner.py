import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from loguru import logger


def run_migrations(postgres_url: str) -> None:
    os.environ["POSTGRES_CONNECTION_STRING"] = postgres_url

    project_root = Path(__file__).parent.parent.parent
    alembic_ini = project_root / "alembic.ini"

    if not alembic_ini.exists():
        logger.warning(f"alembic.ini not found at {alembic_ini}, skipping migrations")
        return

    logger.info("Running database migrations...")
    alembic_cfg = Config(str(alembic_ini))
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations completed")
