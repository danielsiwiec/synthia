import asyncio
import time
from pathlib import Path

from claude_agent_sdk import McpServerConfig
from loguru import logger

from synthia.agents.agent import ClaudeAgent

_FRESH_POOL_SIZE = 2
_SESSION_TTL_SECONDS = 30 * 60
_MAX_SESSION_CACHE_SIZE = 10


class ClaudeAgentPool:
    def __init__(self, mcp_servers: dict[str, McpServerConfig], cwd: str | Path | None = None, enabled: bool = True):
        self._mcp_servers = mcp_servers
        self._cwd = cwd
        self._enabled = enabled
        self._fresh_agents: list[ClaudeAgent] = []
        self._session_cache: dict[str, tuple[ClaudeAgent, float]] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._init_loop_id: int | None = None
        self._non_cacheable_agents: set[int] = set()
        self._init_task: asyncio.Task | None = None
        self._init_lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def create(
        cls,
        mcp_servers: dict[str, McpServerConfig],
        cwd: str | Path | None = None,
        enabled: bool = True,
    ) -> "ClaudeAgentPool":
        pool = cls(mcp_servers, cwd, enabled)

        if not enabled:
            logger.info("Pool disabled, operating in pass-through mode")
            return pool

        pool._init_loop_id = id(asyncio.get_running_loop())
        pool._cleanup_task = asyncio.create_task(pool._cleanup_loop())
        pool._init_task = asyncio.create_task(pool._lazy_init())

        return pool

    async def _lazy_init(self) -> None:
        logger.info(f"Initializing pool with {_FRESH_POOL_SIZE} fresh agents (background)...")
        agents = list(
            await asyncio.gather(*[ClaudeAgent.create(self._mcp_servers, self._cwd) for _ in range(_FRESH_POOL_SIZE)])
        )
        async with self._init_lock:
            self._fresh_agents.extend(agents)
        logger.info(f"Pool initialized with {len(self._fresh_agents)} fresh agents")

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            expired = [
                sid for sid, (_, last_used) in self._session_cache.items() if now - last_used > _SESSION_TTL_SECONDS
            ]
            for sid in expired:
                agent, _ = self._session_cache.pop(sid)
                logger.info(f"Expiring session {sid[:8]}...")
                await agent.disconnect()

    async def _replenish_fresh_agents(self) -> None:
        needed = _FRESH_POOL_SIZE - len(self._fresh_agents)
        if needed > 0:
            logger.info(f"Replenishing {needed} fresh agent(s)...")
            new_agents = await asyncio.gather(
                *[ClaudeAgent.create(self._mcp_servers, self._cwd) for _ in range(needed)]
            )
            self._fresh_agents.extend(new_agents)

    async def acquire(self, resume: str | None = None) -> ClaudeAgent:
        if not self._enabled:
            return await ClaudeAgent.create(self._mcp_servers, self._cwd, resume)

        same_loop = self._init_loop_id is not None and id(asyncio.get_running_loop()) == self._init_loop_id

        if not same_loop:
            logger.info("Different event loop, creating fresh agent...")
            agent = await ClaudeAgent.create(self._mcp_servers, self._cwd, resume)
            self._non_cacheable_agents.add(id(agent))
            return agent

        if resume and resume in self._session_cache:
            agent, _ = self._session_cache.pop(resume)
            logger.info(f"Reusing cached session {resume[:8]}...")
            return agent

        if resume:
            logger.info(f"Connecting to session {resume[:8]}...")
            return await ClaudeAgent.create(self._mcp_servers, self._cwd, resume)

        if self._fresh_agents:
            agent = self._fresh_agents.pop(0)
            logger.info(f"Using fresh agent ({len(self._fresh_agents)} remaining)")
            asyncio.create_task(self._replenish_fresh_agents())
            return agent

        logger.info("No fresh agents, creating new...")
        return await ClaudeAgent.create(self._mcp_servers, self._cwd)

    async def release(self, agent: ClaudeAgent) -> None:
        if not self._enabled:
            await agent.disconnect()
            return

        agent_id = id(agent)
        if agent_id in self._non_cacheable_agents:
            self._non_cacheable_agents.discard(agent_id)
            await agent.disconnect()
            return

        if not agent._session_id:
            await agent.disconnect()
            return

        if len(self._session_cache) >= _MAX_SESSION_CACHE_SIZE:
            oldest_sid = min(self._session_cache, key=lambda k: self._session_cache[k][1])
            old_agent, _ = self._session_cache.pop(oldest_sid)
            logger.info(f"Evicting oldest session {oldest_sid[:8]}... (cache full)")
            await old_agent.disconnect()

        self._session_cache[agent._session_id] = (agent, time.monotonic())
        logger.debug(f"Cached session {agent._session_id[:8]}... ({len(self._session_cache)} total)")

    async def shutdown(self) -> None:
        logger.info("Shutting down pool...")
        for task in [self._cleanup_task, self._init_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        for agent in self._fresh_agents:
            await agent.disconnect()
        for agent, _ in self._session_cache.values():
            await agent.disconnect()
        logger.info("Pool shut down")
