import asyncio
from pathlib import Path

from synthia.agents.agent import Agent, InitMessage, Message, Result, ToolCall
from synthia.agents.skills import build_skill_toolset
from synthia.helpers.pubsub import pubsub


async def _convert_stones_to_pebbles(stones: float) -> str:
    """Convert stones to pebbles. 1 stone = 2.5 pebbles.

    Args:
        stones: The number of stones to convert.
    """
    return f"{stones} stones = {stones * 2.5} pebbles"


async def test_message_parsing():
    messages: list[Message] = []

    def collect(m: Message) -> None:
        messages.append(m)

    pubsub.subscribe(InitMessage, collect)
    pubsub.subscribe(ToolCall, collect)
    pubsub.subscribe(Result, collect)

    await pubsub.start()

    try:
        agent = await Agent.create(cwd=Path(__file__).parent)
        try:
            result = await agent.run_for_result(
                objective="Use the run_bash tool to run: echo 'hello'",
                thread_id=123,
            )
            await asyncio.sleep(0.1)

            assert result is not None
            assert result.success

            init_messages = [m for m in messages if isinstance(m, InitMessage)]
            assert len(init_messages) >= 1, "Expected at least one InitMessage"
            assert init_messages[0].session_id == result.session_id
            assert init_messages[0].thread_id == 123

            tool_calls = [m for m in messages if isinstance(m, ToolCall)]
            assert len(tool_calls) >= 1, "Expected at least one ToolCall"
            bash_call = next((tc for tc in tool_calls if tc.name == "run_bash"), None)
            assert bash_call is not None, "Expected a run_bash tool call"
            assert bash_call.output is not None
            assert "hello" in bash_call.output

            results = [m for m in messages if isinstance(m, Result)]
            assert len(results) >= 1, "Expected at least one Result"
            assert results[-1].success
            assert results[-1].session_id == result.session_id

            assert result.cost_usd is not None, "Expected cost_usd to be set"
            assert result.cost_usd > 0, f"Expected positive cost, got {result.cost_usd}"
        finally:
            await agent.disconnect()
    finally:
        await pubsub.stop()
        pubsub.sync_subscribers[InitMessage].remove(collect)
        pubsub.sync_subscribers[ToolCall].remove(collect)
        pubsub.sync_subscribers[Result].remove(collect)


async def test_multi_turn():
    agent = await Agent.create(cwd=Path(__file__).parent)
    try:
        result1 = await agent.run_for_result(
            objective="Remember: my favorite number is 42. Just confirm.",
            thread_id=456,
        )

        assert result1 is not None
        assert result1.success
        session_id = result1.session_id

        result2 = await agent.run_for_result(
            objective="What is my favorite number? Answer with just the number.",
            thread_id=456,
        )

        assert result2 is not None
        assert result2.success
        assert "42" in result2.result, f"Expected '42' in multi-turn session: {result2.result}"
        assert result2.session_id == session_id, "Multi-turn should keep same session_id"
    finally:
        await agent.disconnect()


async def test_skill_invocation():
    skill_toolset = build_skill_toolset(Path(__file__).parent)
    assert skill_toolset is not None, "Expected the kilo-to-pebble-converter skill to load"

    agent = await Agent.create(cwd=Path(__file__).parent, tools=[skill_toolset])
    try:
        result = await agent.run_for_result(
            objective="Convert 5 kilo to pebble units. Answer with just the number.",
            thread_id=789,
        )

        assert result is not None
        assert result.success
        assert "15.7" in result.result, f"Expected 15.7 (5 × 3.14) in result: {result.result}"
    finally:
        await agent.disconnect()


async def test_function_tool():
    agent = await Agent.create(
        cwd=Path(__file__).parent,
        tools=[_convert_stones_to_pebbles],
    )
    try:
        result = await agent.run_for_result(
            objective="Convert 4 stones to pebbles using the convert tool.",
            thread_id=101,
        )

        assert result is not None
        assert result.success
        assert "10" in result.result, f"Expected 10 (4 × 2.5) in result: {result.result}"
    finally:
        await agent.disconnect()
