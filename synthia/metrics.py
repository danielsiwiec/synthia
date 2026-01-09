import json
from pathlib import Path

import psutil
from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator

_MODEL_PRICING = {
    "claude-opus-4-5-20251101": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,
        "cache_write": 18.75,
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
}

_STATS_CACHE_PATH = Path.home() / ".claude" / "stats-cache.json"


def _calculate_llm_cost() -> float:
    if not _STATS_CACHE_PATH.exists():
        return 0.0

    try:
        stats = json.loads(_STATS_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return 0.0

    total_cost = 0.0
    for model, usage in stats.get("modelUsage", {}).items():
        pricing = _MODEL_PRICING.get(model)
        if not pricing:
            continue

        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)
        cache_read_tokens = usage.get("cacheReadInputTokens", 0)
        cache_write_tokens = usage.get("cacheCreationInputTokens", 0)

        total_cost += input_tokens * pricing["input"] / 1_000_000
        total_cost += output_tokens * pricing["output"] / 1_000_000
        total_cost += cache_read_tokens * pricing["cache_read"] / 1_000_000
        total_cost += cache_write_tokens * pricing["cache_write"] / 1_000_000

    return total_cost


class _MetricsCollector:
    def collect(self):  # type: ignore[override]
        yield GaugeMetricFamily(
            "llm_cost_usd_total", "Total LLM cost in USD based on token usage", value=_calculate_llm_cost()
        )

        total_cpu = 0.0
        total_memory = 0
        count = 0
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                if proc.info["name"] == "claude":
                    total_cpu += proc.info["cpu_percent"] or 0.0
                    if proc.info["memory_info"]:
                        total_memory += proc.info["memory_info"].rss
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        yield GaugeMetricFamily(
            "claude_processes_cpu_percent_total", "Total CPU percentage used by all claude processes", value=total_cpu
        )
        yield GaugeMetricFamily(
            "claude_processes_memory_bytes_total",
            "Total memory in bytes used by all claude processes",
            value=total_memory,
        )
        yield GaugeMetricFamily("claude_processes_count", "Number of running claude processes", value=count)


REGISTRY.register(_MetricsCollector())  # type: ignore[arg-type]


def create_instrumentator() -> Instrumentator:
    return Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )
