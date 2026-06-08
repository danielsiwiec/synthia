import asyncio
import statistics
import time
from pathlib import Path

import pytest
from google.adk.tools.base_toolset import BaseToolset

from synthia.agents.mcp import build_mcp_toolsets

_MCP_CONFIG = Path("mcp_servers.json")
_WARM_REPEATS = 5
_GET_TOOLS_TIMEOUT = 30.0


class _CachedToolset(BaseToolset):
    def __init__(self, inner):
        super().__init__()
        self._inner = inner
        self._cache = None

    async def get_tools(self, readonly_context=None):
        if self._cache is None:
            self._cache = await self._inner.get_tools(readonly_context)
        return self._cache

    async def close(self):
        await self._inner.close()


def _prefix(toolset) -> str:
    return getattr(toolset, "tool_name_prefix", None) or "?"


async def _timed_get_tools(toolset) -> tuple[float, int, str | None]:
    started = time.perf_counter()
    try:
        tools = await asyncio.wait_for(toolset.get_tools(), timeout=_GET_TOOLS_TIMEOUT)
        return time.perf_counter() - started, len(tools), None
    except Exception as error:
        return time.perf_counter() - started, 0, type(error).__name__


async def _gather_get_tools(toolsets) -> tuple[float, list[tuple[float, int, str | None]]]:
    started = time.perf_counter()
    results = await asyncio.gather(*(_timed_get_tools(t) for t in toolsets))
    return time.perf_counter() - started, list(results)


@pytest.mark.performance
async def test_mcp_get_tools_caching_savings():
    toolsets = build_mcp_toolsets(_MCP_CONFIG)
    assert toolsets, "no MCP toolsets configured"
    names = [_prefix(t) for t in toolsets]
    print(f"\n  MCP toolsets: {names}\n")

    cold_wall, cold = await _gather_get_tools(toolsets)
    print("  --- COLD (no warm session: full connect/spawn + list_tools) ---")
    for name, (dur, n, err) in zip(names, cold, strict=False):
        print(f"    {name:12} {dur:7.2f}s  tools={n}  {('ERR=' + err) if err else ''}")
    print(f"    concurrent wall (per-turn cost when cold) = {cold_wall:.2f}s\n")

    warm_per: dict[str, list[float]] = {n: [] for n in names}
    warm_walls: list[float] = []
    for _ in range(_WARM_REPEATS):
        wall, res = await _gather_get_tools(toolsets)
        warm_walls.append(wall)
        for name, (dur, _n, _err) in zip(names, res, strict=False):
            warm_per[name].append(dur)

    print(f"  --- WARM (session pooled, {_WARM_REPEATS} repeats: today's per-turn cost) ---")
    for name in names:
        ts = warm_per[name]
        print(f"    {name:12} median={statistics.median(ts) * 1000:7.1f}ms  max={max(ts) * 1000:7.1f}ms")
    warm_turn = statistics.median(warm_walls)
    print(f"    concurrent wall median (per-turn cost today) = {warm_turn * 1000:.1f}ms\n")

    cached = [_CachedToolset(t) for t in toolsets]
    await _gather_get_tools(cached)
    cached_walls = [(await _gather_get_tools(cached))[0] for _ in range(_WARM_REPEATS)]
    cached_turn = statistics.median(cached_walls)
    print("  --- CACHED (proposed fix: first call delegates, rest return cached) ---")
    print(f"    concurrent wall median (per-turn cost cached) = {cached_turn * 1000:.1f}ms\n")

    saving_warm = warm_turn - cached_turn
    print("  --- SAVINGS per turn ---")
    print(f"    cold (worst case, cold/flaky server) : {cold_wall:.2f}s")
    print(f"    warm steady-state                    : {saving_warm * 1000:.1f}ms")
    print("  --- projected per-session savings (warm steady-state x turns) ---")
    for turns in (1, 3, 5, 10):
        print(f"    {turns:2} turns: {saving_warm * turns * 1000:8.1f}ms")

    for t in toolsets:
        try:
            await t.close()
        except Exception:
            pass
