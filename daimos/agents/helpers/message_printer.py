from collections import defaultdict

from loguru import logger

from daimos.agents.claude import Message, Result, run_for_result


class Summarizer:
    def __init__(self):
        self.sessions = defaultdict(list)

    async def process_message(self, message: Message) -> None:
        session_id = message.session_id
        self.sessions[session_id].append(message)
        if isinstance(message, Result):
            if len(self.sessions) >= 3:
                await self._analyze_similarities()

    async def _analyze_similarities(self) -> None:
        logger.debug(f"Analyzing similarities for {len(self.sessions)} sessions")
        if len(self.sessions) < 3:
            return

        last_3_sessions = list(self.sessions.keys())[-3:]
        analysis_prompt = self._build_analysis_prompt(last_3_sessions)

        logger.debug(f"Analysis prompt: {analysis_prompt}")

        result = await run_for_result(analysis_prompt)
        if result:
            logger.info(f"Similarity analysis and Python script suggestions: {result.result}")

    def _build_analysis_prompt(self, session_ids: list[str]) -> str:
        prompt = """Please inspect the messages from the last 3 sessions and analyze if there are similarities
across these sessions that could be coded in a Python script.

Here are the messages from the 3 sessions:

"""

        for i, session_id in enumerate(session_ids, 1):
            prompt += f"=== SESSION {i} (ID: {session_id}) ===\n"
            if session_id in self.sessions:
                for j, msg in enumerate(self.sessions[session_id], 1):
                    prompt += f"Message {j}: {msg}\n"
            prompt += "\n"

        prompt += """Please analyze these sessions and:

1. Identify patterns, similarities, or repetitive tasks across the sessions
2. Look for common workflows, data processing steps, or automation opportunities
3. Suggest specific Python scripts that could automate or streamline these similar processes
4. Focus on practical, implementable solutions that would save time or reduce manual work

For each suggested Python script, provide:
- A clear description of what it automates
- The key functionality it would implement
- Any specific libraries or approaches that would be useful

Please be specific and actionable in your suggestions."""

        return prompt
