import os

import psutil
from loguru import logger
from prometheus_client import REGISTRY, Counter
from prometheus_client.metrics_core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator

llm_cost_usd_total = Counter("llm_cost_usd_total", "Total LLM cost in USD")


def record_session_cost(cost: float) -> None:
    if cost > 0:
        llm_cost_usd_total.inc(cost)


class _ClaudeProcessCollector:
    def collect(self):
        memory_gauge = GaugeMetricFamily(
            "claude_process_memory_rss_bytes", "RSS memory per Claude subprocess", labels=["pid"]
        )
        cpu_gauge = GaugeMetricFamily(
            "claude_process_cpu_percent", "CPU percentage per Claude subprocess", labels=["pid"]
        )
        count_gauge = GaugeMetricFamily("claude_process_count", "Number of active Claude subprocesses")

        try:
            procs = [
                p
                for p in psutil.process_iter(["pid", "cmdline", "status"])
                if (cmd := p.info.get("cmdline"))
                and os.path.basename(cmd[0]) == "claude"
                and p.info.get("status") != psutil.STATUS_ZOMBIE
            ]
            for p in procs:
                pid = str(p.info["pid"])
                try:
                    memory_gauge.add_metric([pid], p.memory_info().rss)
                    cpu_gauge.add_metric([pid], p.cpu_percent())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            count_gauge.add_metric([], len(procs))
        except Exception as e:
            logger.warning(f"Failed to collect Claude process metrics: {e}")
            count_gauge.add_metric([], 0)

        yield memory_gauge
        yield cpu_gauge
        yield count_gauge


REGISTRY.register(_ClaudeProcessCollector())


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
