import psutil
from loguru import logger
from prometheus_client import Counter, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info

llm_cost_usd_total = Counter("llm_cost_usd_total", "Total LLM cost in USD")

_memory_gauge = Gauge(
    "claude_process_memory_rss_bytes",
    "RSS memory per Claude subprocess",
    ["pid"],
)
_cpu_gauge = Gauge(
    "claude_process_cpu_percent",
    "CPU percentage per Claude subprocess",
    ["pid"],
)
_count_gauge = Gauge(
    "claude_process_count",
    "Number of active Claude subprocesses",
)


def record_session_cost(cost: float) -> None:
    if cost > 0:
        llm_cost_usd_total.inc(cost)


async def _claude_process_metrics(_: Info) -> None:
    _memory_gauge.clear()
    _cpu_gauge.clear()
    try:
        procs = [
            proc
            for proc in psutil.process_iter(["pid", "cmdline", "status"])
            if (cmdline := proc.info.get("cmdline") or [])
            and len(cmdline) > 0
            and cmdline[0] == "claude"
            and proc.info.get("status") != psutil.STATUS_ZOMBIE
        ]
        for proc in procs:
            pid = str(proc.info["pid"])
            _memory_gauge.labels(pid=pid).set(proc.memory_info().rss)
            _cpu_gauge.labels(pid=pid).set(proc.cpu_percent())
        _count_gauge.set(len(procs))
    except Exception as e:
        logger.warning(f"Failed to collect Claude process metrics: {e}")


def create_instrumentator() -> Instrumentator:
    return Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/metrics"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    ).add(_claude_process_metrics)
