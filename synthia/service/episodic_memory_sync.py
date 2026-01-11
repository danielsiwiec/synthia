import asyncio
import os
from pathlib import Path

from claude_agent_sdk.types import ResultMessage
from loguru import logger

from synthia.helpers.pubsub import pubsub

_DEBOUNCE_SECONDS = 30
_PLUGIN_CACHE_DIR = Path.home() / ".claude" / "plugins" / "cache"


def _is_enabled() -> bool:
    return os.getenv("ENABLE_EPISODIC_MEMORY", "").lower() == "true"


def _find_episodic_memory_cli() -> Path | None:
    if not _PLUGIN_CACHE_DIR.exists():
        return None
    for marketplace_dir in _PLUGIN_CACHE_DIR.iterdir():
        matches = list(_PLUGIN_CACHE_DIR.glob(f"{marketplace_dir.name}/episodic-memory/*/cli/episodic-memory.js"))
        if matches:
            return matches[0]
    return None


class EpisodicMemorySyncService:
    def __init__(self, debounce_seconds: int = _DEBOUNCE_SECONDS):
        self._debounce_seconds = debounce_seconds
        self._debounce_task: asyncio.Task | None = None
        self._cli_path: Path | None = None

        if not _is_enabled():
            return

        self._cli_path = _find_episodic_memory_cli()
        if self._cli_path:
            pubsub.subscribe(ResultMessage, self._handle_result)
            logger.info(f"Episodic memory sync service enabled: {self._cli_path}")
        else:
            logger.warning("ENABLE_EPISODIC_MEMORY is set but plugin not found")

    async def _handle_result(self, _message: ResultMessage) -> None:
        self._schedule_sync()

    def _schedule_sync(self) -> None:
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._debounced_sync())

    async def _debounced_sync(self) -> None:
        try:
            await asyncio.sleep(self._debounce_seconds)
            await self._run_sync()
        except asyncio.CancelledError:
            pass

    async def _run_sync(self) -> None:
        if not self._cli_path:
            return
        logger.debug("Running episodic memory sync...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(self._cli_path),
                "sync",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.debug("Episodic memory sync completed")
            else:
                logger.warning(f"Episodic memory sync failed: {stderr.decode()}")
        except Exception as e:
            logger.warning(f"Episodic memory sync error: {e}")
