import psutil
from prometheus_client import REGISTRY, Counter
from prometheus_client.core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator

llm_cost_usd_total = Counter("llm_cost_usd_total", "Total LLM cost in USD")


def record_session_cost(cost: float) -> None:
    if cost > 0:
        llm_cost_usd_total.inc(cost)


class _MetricsCollector:
    def collect(self):  # type: ignore[override]
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
