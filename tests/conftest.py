import os
from pathlib import Path

import pytest
from testcontainers.core.image import DockerImage
from testcontainers.postgres import PostgresContainer

from synthia.helpers.pubsub import pubsub


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def pgvector_container():
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
    workspace_root = Path(__file__).parent.parent
    pgvector_path = workspace_root / "images" / "pgvector"
    with DockerImage(path=str(pgvector_path), clean_up=False) as image:
        with PostgresContainer(str(image)) as postgres:
            connection_url = postgres.get_connection_url(host="127.0.0.1", driver=None)
            yield connection_url


@pytest.fixture
async def clean_pubsub():
    for task in pubsub.tasks:
        task.cancel()
    pubsub.tasks = []
    pubsub.queues.clear()
    yield pubsub
    await pubsub.stop()
