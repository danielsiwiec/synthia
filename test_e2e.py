
import httpx
import pytest

from main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_task_endpoint_basic_math(client):
    response = await client.post("/task", json={"task": "what's 2 + 2?"})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "4" in data["result"]


async def test_task_endpoint_with_schema(client):
    schema = {
        "type": "object",
        "properties": {"result": {"type": "number"}},
        "required": ["result"],
    }

    response = await client.post("/task", json={"task": "what's 2 + 2?", "response_schema": schema})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert isinstance(data["result"], dict)
    assert data["result"]["result"] == 4


async def test_task_endpoint_with_invalid_schema(client):
    invalid_schema = {
        "type": "invalid_type",
        "properties": {"result": {"type": "number"}},
    }

    response = await client.post("/task", json={"task": "what's 2 + 2?", "response_schema": invalid_schema})

    assert response.status_code == 400
    data = response.json()
    assert "Invalid JSON schema" in data["detail"]


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
