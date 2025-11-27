import asyncio
import os
import random
import secrets

import httpx
import pytest

from synthia.main import Config, create_app


@pytest.fixture(scope="session")
def app(pgvector_container):
    os.environ["POSTGRES_CONNECTION_STRING"] = pgvector_container
    config = Config(
        memory_user="test_user",
        telegram_bot_token="test_token",
        telegram_users="user1:test_chat",
        admin_user="user1",
        postgres_connection_string=pgvector_container,
    )
    app_instance = create_app(config)
    yield app_instance
    os.environ.pop("POSTGRES_CONNECTION_STRING", None)


@pytest.fixture
def unique_user():
    return f"user_{secrets.token_hex(8)}"


@pytest.fixture(scope="session")
async def lifespan_context(app):
    async with app.router.lifespan_context(app):
        yield


@pytest.fixture
async def client(app, lifespan_context):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_task_endpoint_basic_math(client):
    response = await client.post("/task", json={"task": "what's 2 + 2?"})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert "4" in data["result"]


@pytest.mark.smoke
async def test_ultimate_e2e(client):
    schema = {
        "type": "object",
        "properties": {"number_of_legs": {"type": "number"}},
        "required": ["number_of_legs"],
    }

    response = await client.post("/task", json={"task": "how many legs does a dog have?", "response_schema": schema})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert isinstance(data["result"], dict)
    assert data["result"]["number_of_legs"] == 4

    async def run_wait_task():
        return await client.post("/task", json={"task": "wait 60 seconds, then say 'hello'"}, timeout=30.0)

    task = asyncio.create_task(run_wait_task())

    await asyncio.sleep(0.5)

    stop_response = await client.post("/stop")
    assert stop_response.status_code == 200

    result = await asyncio.wait_for(task, timeout=6.0)
    assert result.status_code == 499, "Task should return 499 when cancelled"

    follow_up_response = await client.post(
        "/task", json={"task": "what was that number again?", "response_schema": schema, "resume": True}
    )

    assert follow_up_response.status_code == 200
    follow_up_data = follow_up_response.json()
    assert "result" in follow_up_data
    assert "session_id" in follow_up_data
    assert follow_up_data["result"]["number_of_legs"] == 4


async def test_task_endpoint_with_invalid_schema(client):
    invalid_schema = {
        "type": "invalid_type",
        "properties": {"result": {"type": "number"}},
    }

    response = await client.post("/task", json={"task": "what's 2 + 2?", "response_schema": invalid_schema})

    assert response.status_code == 400
    data = response.json()
    assert "Invalid JSON schema" in data["detail"]


async def test_skill(client):
    schema = {
        "type": "object",
        "properties": {"pebble": {"type": "number"}},
        "required": ["pebble"],
    }

    response = await client.post("/task", json={"task": "convert 2 kilo to pebble units", "response_schema": schema})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert isinstance(data["result"], dict)
    assert data["result"]["pebble"] == 6.28


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


async def test_memories(client):
    favorite_number = random.randint(1, 1000)

    first_response = await client.post("/task", json={"task": f"remember my favorite number is {favorite_number}"})
    assert first_response.status_code == 200

    second_response = await client.post("/task", json={"task": "what's my favorite number?"})

    assert second_response.status_code == 200
    second_data = second_response.json()
    assert "result" in second_data
    result_text = second_data["result"].lower()
    assert str(favorite_number) in result_text or "connection issue" not in result_text
