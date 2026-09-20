import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy, Score

from synthia.agents.agent import JEV_MODEL_SPEC
from synthia.metrics import record_call_cost
from synthia.telemetry import start_span

JEV_MODEL = os.getenv("JEV_MODEL", JEV_MODEL_SPEC.name)
JEV_INPUT_COST_PER_M = JEV_MODEL_SPEC.input_cost_per_m
_API_KEY_ENV = "TYPESAFE_API_KEY"
_CALL_TIMEOUT_S = 8.0

Question = Noul | Choice | Score


def jev_available() -> bool:
    return bool(os.getenv(_API_KEY_ENV))


@dataclass
class JevUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latencies_ms: list[int] = field(default_factory=list)

    def add(self, input_tokens: int, latency_ms: int) -> float:
        cost = round(input_tokens / 1_000_000 * JEV_INPUT_COST_PER_M, 8)
        self.record(input_tokens, 0, cost, latency_ms)
        return cost

    def record(self, input_tokens: int, output_tokens: int, cost: float, latency_ms: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd = round(self.cost_usd + cost, 8)
        self.latencies_ms.append(latency_ms)

    @property
    def mean_ms(self) -> int:
        return round(sum(self.latencies_ms) / len(self.latencies_ms)) if self.latencies_ms else 0


class JevClient:
    def __init__(self, api_key: str | None = None, model: str = JEV_MODEL):
        self._model = model
        self._client = AsyncTypeSafeClient(
            api_key=api_key,
            model=model,
            retry=RetryPolicy(max_retries=2, timeout=_CALL_TIMEOUT_S * 3),
            timeout=_CALL_TIMEOUT_S,
        )

    @property
    def model(self) -> str:
        return self._model

    async def ask(self, state: Any, questions: Mapping[str, Question], usage: JevUsage | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        with start_span("jev_call") as span:
            response = await self._client.system_one(state=state, questions=questions)
            latency_ms = int((time.perf_counter() - started) * 1000)
            tokens = (response.usage.input_tokens if response.usage else None) or 0
            cost = round(tokens / 1_000_000 * JEV_INPUT_COST_PER_M, 8)
            if usage is not None:
                usage.add(tokens, latency_ms)
            record_call_cost(self._model, cost)
            span.set_attribute("gen_ai.request.model", self._model)
            span.set_attribute("gen_ai.usage.input_tokens", tokens)
            span.set_attribute("gen_ai.usage.cost_usd", cost)
            span.set_attribute("jev.questions", len(questions))
            span.set_attribute("jev.latency_ms", latency_ms)
        logger.debug(f"🧭 jev {len(questions)} questions, {tokens} tokens, {latency_ms}ms")
        return dict(response.answers)

    async def close(self) -> None:
        await self._client.aclose()
