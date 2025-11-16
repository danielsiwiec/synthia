from datetime import date

from synthia.agents.claude import ClaudeAgent


async def test_run_for_result_current_datetime():
    prompt = """"What is the current date in YYYY-MM-DD format?
    Use bash `date` command to get it and then convert it to the desired format."""
    agent = ClaudeAgent(user="test_user")
    result = await agent.run_for_result(prompt)

    assert result is not None
    assert result.success

    today = date.today().strftime("%Y-%m-%d")
    assert today in result.result, f"Expected today's date {today} not found in result: {result.result}"
