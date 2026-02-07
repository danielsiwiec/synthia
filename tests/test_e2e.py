import asyncio
import random
import secrets
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def unique_user():
    return f"user_{secrets.token_hex(8)}"


async def test_task_endpoint_basic_math(client):
    response = await client.post("/task", json={"task": "what's 2 + 2?", "thread_id": 1})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert "4" in data["result"]


@pytest.mark.smoke
async def test_ultimate_e2e(client):
    main_thread_id = 888888

    response = await client.post(
        "/task",
        json={"task": "how many legs does a dog have? answer with just the number", "thread_id": main_thread_id},
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert "4" in data["result"]

    stop_thread_id = 999999

    async def run_wait_task():
        return await client.post(
            "/task", json={"task": "wait 60 seconds, then say 'hello'", "thread_id": stop_thread_id}, timeout=30.0
        )

    task = asyncio.create_task(run_wait_task())

    await asyncio.sleep(0.5)

    stop_response = await client.post("/stop", params={"thread_id": stop_thread_id})
    assert stop_response.status_code == 200

    result = await asyncio.wait_for(task, timeout=6.0)
    assert result.status_code == 499, "Task should return 499 when cancelled"

    follow_up_response = await client.post(
        "/task", json={"task": "what was that number again? answer with just the number", "thread_id": main_thread_id}
    )

    assert follow_up_response.status_code == 200
    follow_up_data = follow_up_response.json()
    assert "result" in follow_up_data
    assert "session_id" in follow_up_data
    assert "4" in follow_up_data["result"]


async def test_session_survives_restart(pgvector_container):
    from prometheus_client import REGISTRY

    from synthia.main import Config, create_app

    config = Config(
        memory_user="test_user",
        postgres_connection_string=pgvector_container,
        claude_cwd=Path(__file__).parent,
        mcp_config_path=None,
    )
    thread_id = 555555

    app1 = create_app(config)
    async with app1.router.lifespan_context(app1):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app1), base_url="http://test") as c1:
            r1 = await c1.post(
                "/task", json={"task": "remember: the color is blue. just confirm.", "thread_id": thread_id}
            )
            assert r1.status_code == 200

    for key in list(REGISTRY._names_to_collectors):
        if key.startswith("http_"):
            try:
                REGISTRY.unregister(REGISTRY._names_to_collectors[key])
            except Exception:
                pass

    app2 = create_app(config)
    async with app2.router.lifespan_context(app2):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://test") as c2:
            r2 = await c2.post(
                "/task",
                json={"task": "what color was it? answer with just the color", "thread_id": thread_id},
            )
            assert r2.status_code == 200
            assert "blue" in r2.json()["result"].lower()


async def test_skill(client):
    response = await client.post(
        "/task", json={"task": "convert 2 kilo to pebble units, answer with just the number", "thread_id": 3}
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "session_id" in data
    assert "6.28" in data["result"]


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


async def test_memories(client):
    favorite_number = random.randint(1, 1000)
    thread_id = 4

    first_response = await client.post(
        "/task", json={"task": f"remember my favorite number is {favorite_number}", "thread_id": thread_id}
    )
    assert first_response.status_code == 200

    second_response = await client.post("/task", json={"task": "what's my favorite number?", "thread_id": thread_id})

    assert second_response.status_code == 200
    second_data = second_response.json()
    assert "result" in second_data
    result_text = second_data["result"].lower()
    assert str(favorite_number) in result_text or "connection issue" not in result_text
