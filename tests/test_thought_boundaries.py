import asyncio
from pathlib import Path

import pytest

from synthia.agents.agent import Agent, Thought
from synthia.helpers.pubsub import pubsub

_BLOCK_START = ('"', "'", "(", "[", "#", "-", "*", ">", "`")


def _objective(seed: int) -> str:
    # Multi-step tool use reliably triggers interleaved thinking (the beta reasons around tool
    # calls), and a long thinking block is what ADK streams as several thought parts — the case
    # boundary detection must merge. Varying the numbers keeps retries decorrelated (uncached).
    a, b, c = 17 + seed, 23 + seed, 100 + seed
    return (
        f"Use run_bash to compute {a}*{b}. Then use run_bash again to add {c} to that result. "
        f"Think carefully and in detail, step by step, before and after each command, then tell "
        f"me the final number."
    )


def _starts_a_new_block(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    return s[0].isupper() or s[0].isdigit() or s[0] in _BLOCK_START


async def test_published_thoughts_are_complete_blocks(monkeypatch):
    monkeypatch.setattr("synthia.agents.agent._THINKING_BUDGET", 4096)
    monkeypatch.setattr("synthia.agents.agent._PROMPT_CACHING", False)

    thoughts: list[Thought] = []
    pubsub.subscribe(Thought, thoughts.append)
    await pubsub.start()

    try:
        agent = await Agent.create(cwd=Path(__file__).parent)
        try:
            # Interleaved thinking is advisory — the model occasionally answers without any thinking
            # block, which makes the contract vacuous. Retry (with a fresh prompt) until it reasons.
            for attempt in range(4):
                thoughts.clear()
                result = await agent.run_for_result(objective=_objective(attempt), thread_id=271828 + attempt)
                await asyncio.sleep(0.1)
                assert result is not None and result.success
                if thoughts:
                    break
        finally:
            await agent.disconnect()

        if not thoughts:
            pytest.skip("model emitted no thinking across retries — boundary contract not assessable")

        # A complete reasoning block always begins at a sentence/structure boundary. A thought that
        # starts mid-sentence (a lowercase word or trailing punctuation) is a stream fragment the
        # boundary detection failed to merge into its parent block.
        fragments = [t.thinking for t in thoughts if not _starts_a_new_block(t.thinking)]
        assert not fragments, (
            f"every published thought must be a complete reasoning block, but "
            f"{len(fragments)}/{len(thoughts)} began mid-sentence (un-merged fragments):\n"
            + "\n".join(f"  - {f!r}" for f in fragments)
        )
    finally:
        await pubsub.stop()
        pubsub.sync_subscribers[Thought].remove(thoughts.append)
