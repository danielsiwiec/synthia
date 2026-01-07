import psutil
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

_claude_cpu_percent = Gauge(
    "claude_processes_cpu_percent_total",
    "Total CPU percentage used by all claude processes",
)

_claude_memory_bytes = Gauge(
    "claude_processes_memory_bytes_total",
    "Total memory in bytes used by all claude processes",
)

_claude_process_count = Gauge(
    "claude_processes_count",
    "Number of running claude processes",
)


def _collect_claude_process_metrics():
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

    _claude_cpu_percent.set(total_cpu)
    _claude_memory_bytes.set(total_memory)
    _claude_process_count.set(count)


def create_instrumentator() -> Instrumentator:
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )

    instrumentator.add(
        lambda info: _collect_claude_process_metrics(),
    )

    return instrumentator
