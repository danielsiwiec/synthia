import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    McpServerConfig,
    ResultMessage,
    SystemMessage,
    UserMessage,
)
from loguru import logger
from pydantic import BaseModel

from synthia.helpers.pubsub import pubsub
from synthia.metrics import record_session_cost
from synthia.telemetry import current_span, start_span, traced

_FRESH_POOL_SIZE = 2
_SESSION_TTL_SECONDS = 30 * 60

SYSTEM_PROMPT = f"""
Your name is Synthia. You are a helpful assistant that can help with tasks and questions.

# Today is {datetime.now().strftime("%Y-%m-%d")}.

## Browser downloads
All browser downloads, by default, are saved in the `/mounts/downloads` folder.

## Web Search
If you encounter access issues using the web search tool, try using the browser instead.
"""


class ToolCall(BaseModel):
    session_id: str
    thread_id: int | None = None
    name: str
    input: dict
    output: str | None = None
    error: str | None = None

    def render(self, short: bool = False) -> str:
        parts = [f"🔧 [{self.name}] input={self.input}"]
        if not short and self.output is not None:
            parts.append(f"output='{self.output}'")
        if self.error is not None:
            parts.append(f"error='{self.error}'")
        return " ".join(parts)


class Result(BaseModel):
    session_id: str
    thread_id: int | None = None
    success: bool
    result: str
    error: str | None = None

    def render(self, short: bool = False) -> str:
        return f"{'✅' if self.success else '🔴'} {self.result if self.success else self.error}"


class InitMessage(BaseModel):
    session_id: str
    thread_id: int | None = None
    prompt: str

    def render(self, short: bool = False) -> str:
        return f"⚙️ {self.prompt}"


class Thought(BaseModel):
    session_id: str
    thread_id: int | None = None
    thinking: str

    def render(self, short: bool = False) -> str:
        preview = self.thinking[:100] + "..." if len(self.thinking) > 100 else self.thinking
        return f"💭 {preview}"


Message = ToolCall | Result | InitMessage | Thought


class ClaudeClientPool:
    def __init__(self, mcp_servers: dict[str, McpServerConfig], cwd: str | Path | None = None):
        self._mcp_servers = mcp_servers
        self._cwd = cwd
        self._fresh_clients: list[ClaudeSDKClient] = []
        self._session_cache: dict[str, tuple[ClaudeSDKClient, float]] = {}  # session_id -> (client, last_used)
        self._cleanup_task: asyncio.Task | None = None
        self._init_loop_id: int | None = None

    def _create_options(self, resume: str | None = None) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            cwd=self._cwd,
            setting_sources=["user", "project"],
            allowed_tools=["Skill"],
            permission_mode="bypassPermissions",
            system_prompt=SYSTEM_PROMPT,
            resume=resume,
            mcp_servers=self._mcp_servers,
        )

    async def _connect_client(self, resume: str | None = None) -> ClaudeSDKClient:
        client = ClaudeSDKClient(self._create_options(resume))
        logger.debug("🔌 Claude SDK connecting...")
        await client.connect()
        logger.debug("🔌 Claude SDK connected")
        return client

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            expired = [
                sid for sid, (_, last_used) in self._session_cache.items() if now - last_used > _SESSION_TTL_SECONDS
            ]
            for sid in expired:
                client, last_used = self._session_cache.pop(sid)
                logger.info(f"Expiring session {sid[:8]}... (idle {int(now - last_used)}s)")
                await self._safe_disconnect(client)

    async def _replenish_fresh_clients(self) -> None:
        needed = _FRESH_POOL_SIZE - len(self._fresh_clients)
        if needed > 0:
            logger.info(f"Replenishing {needed} fresh client(s)...")
            new_clients = await asyncio.gather(*[self._connect_client() for _ in range(needed)])
            self._fresh_clients.extend(new_clients)

    async def initialize(self, skip_prewarm: bool = False) -> None:
        self._init_loop_id = id(asyncio.get_running_loop())
        if skip_prewarm:
            logger.info("Pool initialized without pre-warming")
        else:
            logger.info(f"Initializing pool with {_FRESH_POOL_SIZE} fresh clients...")
            self._fresh_clients = list(await asyncio.gather(*[self._connect_client() for _ in range(_FRESH_POOL_SIZE)]))
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info(f"Pool initialized with {len(self._fresh_clients)} fresh clients")

    async def execute(self, prompt: str, resume: str | None = None) -> AsyncIterator[Any]:
        same_loop = id(asyncio.get_running_loop()) == self._init_loop_id

        if not same_loop:
            logger.info("Different event loop, creating fresh client...")
            client = await self._connect_client(resume=resume)
        elif resume and resume in self._session_cache:
            client, _ = self._session_cache.pop(resume)
            logger.info(f"Reusing cached session {resume[:8]}...")
        elif resume:
            logger.info(f"Connecting to session {resume[:8]}...")
            client = await self._connect_client(resume=resume)
        elif self._fresh_clients:
            client = self._fresh_clients.pop(0)
            logger.info(f"Using fresh client ({len(self._fresh_clients)} remaining)")
            asyncio.create_task(self._replenish_fresh_clients())
        else:
            logger.info("No fresh clients, connecting new...")
            client = await self._connect_client()

        session_id: str | None = None

        try:
            logger.debug(f"📤 Claude SDK query: {prompt[:50]}...")
            await client.query(prompt=prompt)
            logger.debug("📤 Claude SDK query sent, receiving messages...")

            async for message in client.receive_messages():
                if isinstance(message, SystemMessage):
                    session_id = message.data.get("session_id")
                if isinstance(message, ResultMessage):
                    logger.debug(f"📥 Claude SDK ResultMessage received: {(message.result or '')[:50]}...")
                    cost = getattr(message, "total_cost_usd", None)
                    usage = getattr(message, "usage", None)
                    logger.info(f"💰 Session cost: ${cost}, usage: {usage}")
                    if cost:
                        record_session_cost(cost)
                yield message
                if isinstance(message, ResultMessage):
                    break
        finally:
            if not same_loop:
                await self._safe_disconnect(client)
            elif session_id:
                self._session_cache[session_id] = (client, time.monotonic())
                logger.debug(f"Cached session {session_id[:8]}... ({len(self._session_cache)} total)")

    async def _safe_disconnect(self, client: ClaudeSDKClient) -> None:
        try:
            await client.disconnect()
        except Exception:
            pass

    async def shutdown(self) -> None:
        logger.info("Shutting down pool...")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        for client in self._fresh_clients:
            await self._safe_disconnect(client)
        for client, _ in self._session_cache.values():
            await self._safe_disconnect(client)
        logger.info("Pool shut down")


class ClaudeAgent:
    def __init__(
        self,
        mcp_servers: dict[str, McpServerConfig] | None = None,
        cwd: str | Path | None = None,
    ):
        self._mcp_servers = mcp_servers or {}
        self._cwd = cwd
        self._pool: ClaudeClientPool | None = None

    async def initialize_pool(self, skip_prewarm: bool = False) -> None:
        self._pool = ClaudeClientPool(self._mcp_servers, self._cwd)
        await self._pool.initialize(skip_prewarm=skip_prewarm)

    async def shutdown_pool(self) -> None:
        if self._pool:
            await self._pool.shutdown()

    def _parse_message(
        self, message: Any, tool_calls: dict[str, ToolCall], session_id: str, thread_id: int | None
    ) -> Any | None:
        if isinstance(message, ResultMessage):
            return Result(
                session_id=message.session_id,
                thread_id=thread_id,
                success=message.subtype == "success",
                result=message.result.strip(),
            )

        if not isinstance(message, (UserMessage, AssistantMessage)):
            return None

        content_blocks = getattr(message, "content", [])
        if not isinstance(content_blocks, list):
            return None

        for block in content_blocks:
            match type(block).__name__:
                case "ThinkingBlock":
                    thinking = getattr(block, "thinking", "")
                    if thinking:
                        return Thought(
                            session_id=session_id,
                            thread_id=thread_id,
                            thinking=thinking,
                        )

                case "ToolUseBlock":
                    tool_use_id = getattr(block, "id", None)
                    if tool_use_id:
                        tool_calls[tool_use_id] = ToolCall(
                            session_id=session_id,
                            thread_id=thread_id,
                            name=getattr(block, "name", ""),
                            input=getattr(block, "input", {}),
                        )

                case "ToolResultBlock":
                    tool_use_id = getattr(block, "tool_use_id", None)
                    output = getattr(block, "content", "")
                    if isinstance(output, list):
                        output = str(output)
                    elif output is None:
                        output = ""

                    if tool_use_id and tool_use_id in tool_calls:
                        tool_call = tool_calls.pop(tool_use_id)
                        return ToolCall(
                            session_id=tool_call.session_id,
                            thread_id=tool_call.thread_id,
                            name=tool_call.name,
                            input=tool_call.input,
                            output=output.strip(),
                            error="Error occurred" if getattr(block, "is_error", False) else None,
                        )

        return None

    async def _run(
        self,
        objective: str,
        thread_id: int,
        resume_from_session: str | None = None,
    ) -> AsyncIterator[Any]:
        if self._pool is None:
            raise RuntimeError("Pool not initialized. Call initialize_pool() first.")

        prompt_with_thread_id = f"{objective}\n\nthread_id: {thread_id}"
        tool_calls: dict[str, ToolCall] = {}
        session_id = None

        async for message in self._pool.execute(prompt_with_thread_id, resume=resume_from_session):
            await pubsub.publish(message)
            if isinstance(message, SystemMessage):
                session_id = message.data["session_id"]
                yield InitMessage(session_id=session_id, thread_id=thread_id, prompt=objective)
                continue
            if session_id is None:
                raise ValueError("Session ID is not set")
            if transformed := self._parse_message(message, tool_calls, session_id, thread_id):
                yield transformed
                if isinstance(transformed, Result):
                    break

    @traced("claude_run")
    async def run_for_result(
        self,
        objective: str,
        thread_id: int,
        resume_from_session: str | None = None,
    ) -> Result | None:
        message_count = 0
        async for message in self._run(objective, resume_from_session=resume_from_session, thread_id=thread_id):
            message_count += 1
            message_type = type(message).__name__
            with start_span(message_type):
                await pubsub.publish(message)
            if isinstance(message, Result):
                current_span().set_attribute("message_count", message_count)
                return message
