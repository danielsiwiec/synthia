from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path

import asyncpg
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from loguru import logger

from synthia.agents.agent import InitMessage, Message, Result, Thought, ToolCall
from synthia.agents.episodic.db import generate_embedding
from synthia.telemetry import start_span, traced

_SUMMARIZATION_MARKER = "[EPISODIC_SUMMARIZATION]"


class EpisodicMemoryService:
    def __init__(self, pool: asyncpg.Pool, cwd: str | Path | None = None):
        self._pool = pool
        self._cwd = cwd
        self._transcripts_by_session: dict[str, list[str]] = defaultdict(list)
        self._prompts_by_session: dict[str, str] = {}

    def _is_summarization_session(self, prompt: str) -> bool:
        return _SUMMARIZATION_MARKER in prompt

    @traced("episodic_memory.summarize_and_store")
    async def _summarize_and_store(self, session_id: str, transcript: str, original_prompt: str) -> None:
        summarization_prompt = f"""{_SUMMARIZATION_MARKER}
Summarize the following conversation transcript in 2-3 sentences. Focus on:
- What task was requested
- What actions were taken
- What was the outcome

Respond with ONLY the summary, no additional text.

Original request: {original_prompt}

Transcript:
{transcript[:8000]}
"""

        try:
            options = ClaudeAgentOptions(
                cwd=self._cwd,
                permission_mode="bypassPermissions",
            )
            client = ClaudeSDKClient(options)
            await client.connect()

            try:
                with start_span("episodic_memory.claude_summarization") as span:
                    span.set_attribute("session_id", session_id[:8])
                    await client.query(prompt=summarization_prompt)
                    summary = None
                    async for message in client.receive_messages():
                        if isinstance(message, ResultMessage):
                            summary = message.result
                            break
            finally:
                await client.disconnect()

            if not summary:
                logger.error(f"Failed to summarize session {session_id[:8]}: no result")
                return

            combined_text = f"{summary}\n\n{transcript[:4000]}"
            embedding = generate_embedding(combined_text)

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO conversations (transcript, summary, embedding)
                    VALUES ($1, $2, $3::vector)
                    """,
                    transcript,
                    summary,
                    json.dumps(embedding),
                )

            logger.info(f"Stored episodic memory for session {session_id[:8]}")

        except Exception as e:
            logger.error(f"Error storing episodic memory for session {session_id[:8]}: {e}")

    @traced("episodic_memory.track_message")
    async def track_message(self, message: Message) -> None:
        if isinstance(message, InitMessage):
            if self._is_summarization_session(message.prompt):
                return
            self._transcripts_by_session[message.session_id] = [f"User: {message.prompt}"]
            self._prompts_by_session[message.session_id] = message.prompt
            return

        session_id = message.session_id

        if session_id not in self._transcripts_by_session:
            return

        if isinstance(message, Result):
            transcript = "\n".join(self._transcripts_by_session[session_id])
            original_prompt = self._prompts_by_session.get(session_id, "")

            self._transcripts_by_session.pop(session_id, None)
            self._prompts_by_session.pop(session_id, None)

            if message.success:
                transcript += f"\nResult: {message.result}"
            else:
                transcript += f"\nError: {message.error}"

            asyncio.create_task(self._summarize_and_store(session_id, transcript, original_prompt))
            return

        if isinstance(message, ToolCall):
            if message.output:
                self._transcripts_by_session[session_id].append(
                    f"Tool [{message.name}]: {message.input} -> {message.output[:500]}"
                )
            else:
                self._transcripts_by_session[session_id].append(f"Tool [{message.name}]: {message.input}")
        elif isinstance(message, Thought):
            self._transcripts_by_session[session_id].append(f"Thinking: {message.thinking[:200]}")
