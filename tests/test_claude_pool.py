from pathlib import Path

from synthia.agents.pool import ClaudeAgentPool


async def test_pool_session_resumption():
    pool1 = await ClaudeAgentPool.create(mcp_servers={}, cwd=Path(__file__).parent)
    try:
        agent1 = await pool1.acquire()
        result1 = await agent1.run_for_result(
            objective="Remember this: my favorite color is purple. Just confirm you've noted it.",
            thread_id=789,
        )
        await pool1.release(agent1)

        assert result1 is not None
        assert result1.success
        session_id = result1.session_id
    finally:
        await pool1.shutdown()

    pool2 = await ClaudeAgentPool.create(mcp_servers={}, cwd=Path(__file__).parent)
    try:
        agent2 = await pool2.acquire(resume=session_id)
        result2 = await agent2.run_for_result(
            objective="What is my favorite color? Answer with just the color name.",
            thread_id=789,
        )
        await pool2.release(agent2)

        assert result2 is not None
        assert result2.success
        assert "purple" in result2.result.lower(), f"Expected 'purple' in result: {result2.result}"
    finally:
        await pool2.shutdown()
