import asyncio
import struct
import time
import zlib
from collections.abc import Callable
from pathlib import Path

from loguru import logger


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def write_band_png(path: Path, top: tuple[int, int, int], bottom: tuple[int, int, int], size: int = 96) -> Path:
    half = size // 2
    rows = [bytes(top) * size if y < half else bytes(bottom) * size for y in range(size)]
    raw = b"".join(b"\x00" + row for row in rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return path


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
