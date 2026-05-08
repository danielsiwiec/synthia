import secrets
import time

import pytest
from mem0 import AsyncMemory

from synthia.agents.memory.client import _mem0_config

_ITERATIONS = 3


@pytest.fixture(scope="module")
async def memory_client(pgvector_container, ollama_container):
    return AsyncMemory.from_config(_mem0_config(pgvector_container, ollama_container))


@pytest.mark.performance
async def test_memory_add_performance(memory_client):
    user_id = f"perf_{secrets.token_hex(4)}"
    timings = []

    for i in range(_ITERATIONS):
        content = f"My favorite city number {i} is {secrets.token_hex(4)}"
        messages = [{"role": "user", "content": content}]

        start = time.perf_counter()
        await memory_client.add(messages, user_id=user_id, infer=False)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    mean = sum(timings) / len(timings)
    print(f"\n[ollama] memory.add — mean: {mean:.3f}s, times: {[f'{t:.3f}s' for t in timings]}")


@pytest.mark.performance
async def test_memory_search_performance(memory_client):
    user_id = f"perf_{secrets.token_hex(4)}"

    for _i in range(5):
        messages = [{"role": "user", "content": f"I enjoy hiking in mountain range {secrets.token_hex(4)}"}]
        await memory_client.add(messages, user_id=user_id, infer=False)

    timings = []
    queries = ["hiking", "mountains", "favorite outdoor activity"]

    for query in queries:
        start = time.perf_counter()
        await memory_client.search(query, filters={"user_id": user_id})
        elapsed = time.perf_counter() - start
        timings.append(elapsed)

    mean = sum(timings) / len(timings)
    print(f"\n[ollama] memory.search — mean: {mean:.3f}s, times: {[f'{t:.3f}s' for t in timings]}")
