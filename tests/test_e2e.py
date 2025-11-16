import random
import secrets

import httpx
import pytest

from synthia.main import Config, create_app


@pytest.fixture
def app():
    random_user = f"user_{secrets.token_hex(8)}"
    config: Config = {"memory_user": random_user, "telegram_bot_token": "test_token", "telegram_chat_id": "test_chat"}
    return create_app(config)


@pytest.fixture
async def client(app):
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
async def test_task_endpoint_with_schema(client):
    schema = {
        "type": "object",
        "properties": {"number_of_legs": {"type": "number"}},
        "required": ["number_of_legs"],
    }

    # First request
    response = await client.post("/task", json={"task": "how many legs does a dog have?", "response_schema": schema})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert isinstance(data["result"], dict)
    assert data["result"]["number_of_legs"] == 4

    data["session_id"]

    # Test that resume parameter is accepted (even if session doesn't exist)
    # This verifies the resume functionality is properly integrated
    follow_up_response = await client.post(
        "/task", json={"task": "what was that number again?", "response_schema": schema, "resume": True}
    )

    assert follow_up_response.status_code == 200
    follow_up_data = follow_up_response.json()
    assert "result" in follow_up_data
    assert "session_id" in follow_up_data
    assert follow_up_data["result"]["number_of_legs"] == data["result"]["number_of_legs"]


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

    await client.post("/task", json={"task": f"remember my favorite number is {favorite_number}"})

    second_response = await client.post("/task", json={"task": "what's my favorite number?"})

    assert second_response.status_code == 200
    second_data = second_response.json()
    assert "result" in second_data
    assert str(favorite_number) in second_data["result"]
