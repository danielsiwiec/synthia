import random
import statistics
import time

import pytest

_REPEATS = 5
_first_times: list[float] = []
_followup_times: list[float] = []


def _print_stats(label: str, times: list[float]) -> None:
    print(
        f"  {label}:  mean={statistics.mean(times):.1f}s  stdev={statistics.stdev(times):.1f}s  "
        f"min={min(times):.1f}s  max={max(times):.1f}s"
    )


@pytest.mark.performance
@pytest.mark.repeat(_REPEATS)
async def test_conversation_performance(client):
    thread_id = random.randint(100000, 999999)

    t0 = time.perf_counter()
    r1 = await client.post("/task", json={"task": "what's 2+2? answer with just the number", "thread_id": thread_id})
    t1 = time.perf_counter()

    assert r1.status_code == 200
    assert "4" in r1.json()["result"]

    r2 = await client.post(
        "/task",
        json={"task": "what's that number times 3? answer with just the number", "thread_id": thread_id},
    )
    t2 = time.perf_counter()

    assert r2.status_code == 200
    assert "12" in r2.json()["result"]

    first = t1 - t0
    followup = t2 - t1
    _first_times.append(first)
    _followup_times.append(followup)

    run = len(_first_times)
    print(f"\n  Run {run}/{_REPEATS}: first={first:.1f}s  follow-up={followup:.1f}s")

    if run == _REPEATS:
        print(f"\n  --- Stats ({_REPEATS} runs) ---")
        _print_stats("First message", _first_times)
        _print_stats("Follow-up   ", _followup_times)
