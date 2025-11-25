import asyncio
import time
from collections.abc import Callable

from loguru import logger


async def await_until(func: Callable[[], bool], name: str, poll_delay: float = 0.5, timeout: int = 120) -> None:
    def done() -> bool:
        try:
            return func()
        except Exception as e:
            logger.debug(f"[{name}]: exception while waiting: {e}")
            return False

    await asyncio.sleep(poll_delay)

    wait_start = time.time()
    while time.time() - wait_start < timeout:
        logger.debug(f"[{name}]: waiting...")
        if done():
            wait_time = time.time() - wait_start
            log_func = logger.debug if wait_time < 10 else (logger.info if wait_time < 60 else logger.warning)
            log_func(f"[{name}]: waiting complete within {round(wait_time, 2)} seconds")
            return
        await asyncio.sleep(0.5)

    logger.error(f"[{name}]: waiting didn't finish within {timeout} seconds")
    raise AssertionError(f"[{name}]: waiting didn't finish within {timeout} seconds")
