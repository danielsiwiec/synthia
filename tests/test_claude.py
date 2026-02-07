import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from synthia.agents.agent import ClaudeAgent, InitMessage, Message, Result, ToolCall
from synthia.helpers.pubsub import pubsub


def _create_converter_mcp_server():
    @tool(
        "convert-stones-to-pebbles",
        "Convert stones to pebbles. 1 stone = 2.5 pebbles.",
        {
            "type": "object",
            "properties": {
                "stones": {
                    "type": "number",
                    "description": "The number of stones to convert",
                },
            },
            "required": ["stones"],
        },
    )
    async def convert_stones_to_pebbles(args: dict[str, Any]) -> dict[str, Any]:
        stones = args["stones"]
        pebbles = stones * 2.5
        return {"result": f"{stones} stones = {pebbles} pebbles"}

    return create_sdk_mcp_server(name="converter", version="0.0.1", tools=[convert_stones_to_pebbles])


async def test_message_parsing():
    messages: list[Message] = []

    def collect(m: Message) -> None:
        messages.append(m)

    pubsub.subscribe(InitMessage, collect)
    pubsub.subscribe(ToolCall, collect)
    pubsub.subscribe(Result, collect)

    await pubsub.start()

    try:
        agent = await ClaudeAgent.create(cwd=Path(__file__).parent)
        try:
            result = await agent.run_for_result(
                objective="Use bash to run: echo 'hello'",
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
            bash_call = next((tc for tc in tool_calls if tc.name == "Bash"), None)
            assert bash_call is not None, "Expected a Bash tool call"
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
    agent = await ClaudeAgent.create(cwd=Path(__file__).parent)
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
    agent = await ClaudeAgent.create(cwd=Path(__file__).parent)
    try:
        result = await agent.run_for_result(
            objective="Convert 5 kilo to pebble units.",
            thread_id=789,
        )

        assert result is not None
        assert result.success
        assert "15.7" in result.result, f"Expected 15.7 (5 × 3.14) in result: {result.result}"
    finally:
        await agent.disconnect()


async def test_mcp_server():
    mcp_server = _create_converter_mcp_server()
    agent = await ClaudeAgent.create(
        cwd=Path(__file__).parent,
        mcp_servers={"converter": mcp_server},
    )
    try:
        result = await agent.run_for_result(
            objective="Convert 4 stones to pebbles using the converter tool.",
            thread_id=101,
        )

        assert result is not None
        assert result.success
        assert "10" in result.result, f"Expected 10 (4 × 2.5) in result: {result.result}"
    finally:
        await agent.disconnect()
