import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from docker.errors import NotFound
from testcontainers.core.image import DockerImage
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@contextmanager
def _safe_container_context(container):
    try:
        with container:
            yield container
    except NotFound:
        pass


@pytest.fixture(scope="session")
def pgvector_container():
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
    workspace_root = Path(__file__).parent.parent
    pgvector_path = workspace_root / "images" / "pgvector"
    with DockerImage(path=str(pgvector_path), clean_up=False) as image:
        with PostgresContainer(str(image)) as postgres:
            connection_url = postgres.get_connection_url(host="127.0.0.1", driver=None)
            yield connection_url
