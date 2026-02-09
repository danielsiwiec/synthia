import random

import pytest


@pytest.mark.eval
async def test_memory_store_and_retrieve(client):
    secret = random.randint(1000, 9999)
    store_thread = random.randint(100000, 199999)
    retrieve_thread = random.randint(200000, 299999)

    store_response = await client.post(
        "/task",
        json={"task": f"Remember that my secret code is {secret}", "thread_id": store_thread},
    )
    assert store_response.status_code == 200

    retrieve_response = await client.post(
        "/task",
        json={"task": "What is my secret code? Answer with just the number.", "thread_id": retrieve_thread},
    )
    assert retrieve_response.status_code == 200
    result = retrieve_response.json()["result"]
    assert str(secret) in result
