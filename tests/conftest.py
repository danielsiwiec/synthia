import os
from pathlib import Path

os.environ["LANGSMITH_PROJECT"] = "tests"
os.environ.pop("CLAUDECODE", None)

import httpx
import ollama as ollama_client
import pytest
from testcontainers.core.image import DockerImage
from testcontainers.ollama import OllamaContainer
from testcontainers.postgres import PostgresContainer

from synthia.agents.memory.client import OLLAMA_EMBEDDING_MODEL
from synthia.helpers.pubsub import pubsub
from synthia.main import Config, create_app


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


@pytest.fixture(scope="session")
def ollama_container():
    models_cache = Path(__file__).parent.parent / ".ollama-models"
    models_cache.mkdir(exist_ok=True)
    container = OllamaContainer("ollama/ollama")
    container.with_volume_mapping(str(models_cache), "/root/.ollama/models", mode="rw")
    with container as ollama:
        client = ollama_client.Client(host=ollama.get_endpoint())
        client.pull(OLLAMA_EMBEDDING_MODEL)
        yield ollama.get_endpoint()


@pytest.fixture(scope="session")
def app(pgvector_container, ollama_container):
    os.environ["POSTGRES_CONNECTION_STRING"] = pgvector_container
    config = Config(
        postgres_connection_string=pgvector_container,
        ollama_url=ollama_container,
        claude_cwd=Path(__file__).parent,
        mcp_config_path=None,
    )
    app_instance = create_app(config)
    yield app_instance
    os.environ.pop("POSTGRES_CONNECTION_STRING", None)


@pytest.fixture(scope="session")
async def lifespan_context(app):
    async with app.router.lifespan_context(app):
        yield


@pytest.fixture
async def client(app, lifespan_context):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def clean_pubsub():
    for task in pubsub.tasks:
        task.cancel()
    pubsub.tasks = []
    pubsub.queues.clear()
    pubsub.async_subscribers.clear()
    pubsub.sync_subscribers.clear()
    yield pubsub
    await pubsub.stop()
