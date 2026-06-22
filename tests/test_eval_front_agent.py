import asyncio
import os
import uuid
from dataclasses import dataclass, field
from time import perf_counter

import pytest

from synthia.agents.agent import FRONT_MODEL, Agent, build_front_instruction

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="front agent eval needs OPENAI_API_KEY"),
]

# Tweak these to evaluate different front-agent configurations.
EVAL_MODEL = os.getenv("EVAL_FRONT_MODEL", FRONT_MODEL)
EVAL_RUNS = int(os.getenv("EVAL_RUNS", "4"))
EVAL_INSTRUCTION = None  # set to a string to override the front system prompt

KAVITA = {
    "id": "task-kavita",
    "label": "Kavita ratings",
    "request": "rate my Kavita library",
    "result": "Rated 120 books in Kavita.",
    "status": "done",
}
MAGAZINE = {
    "id": "task-magazine-001",
    "label": "Magazine check",
    "request": "check my magazine issues",
    "result": "The Atlantic June 2026 is current; Wired needs the July issue.",
    "status": "done",
}
MAGAZINE_CANCEL = {
    "id": "task-mag-cancel",
    "label": "Cancel magazine subscription",
    "request": "cancel my Wired magazine subscription",
    "result": "Started cancelling the Wired subscription; awaiting confirmation.",
    "status": "done",
}
VACUUM = {
    "id": "task-vacuum-77",
    "label": "Robot vacuum comparison",
    "request": "compare the Roborock Saros 10R and the Roomba Combo",
    "result": "The Roborock Saros 10R edges out the Roomba Combo on mopping and obstacle avoidance.",
    "status": "done",
}
RUG = {
    "id": "task-rug-9",
    "label": "Persian rug",
    "request": "describe the rug in this photo",
    "result": "A black medallion Persian-style rug with cream floral borders.",
    "status": "done",
}
TV = {
    "id": "task-tv-3",
    "label": "TV upgrade",
    "request": "is there a newer TV than my A95L",
    "result": "The Sony BRAVIA 9 (2024) is the newer flagship above the A95L.",
    "status": "done",
}
GARMIN_CONV = {
    "id": "conv-garmin",
    "summary": "Discussed the Garmin FR970 falsely logging sleep and stairs; decided to update the firmware to fix it.",
    "transcript": "User reported FR970 false sleep detection. We agreed updating the firmware should resolve it.",
}


@dataclass
class EvalResult:
    passed: bool
    duration_s: float
    detail: str = ""


@dataclass
class StubWorld:
    seed_tasks: list[dict] = field(default_factory=list)
    history_tasks: list[dict] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)
    conversations: list[dict] = field(default_factory=list)
    memories: list[dict] = field(default_factory=list)
    model: str = EVAL_MODEL
    instruction: str | None = EVAL_INSTRUCTION

    def __post_init__(self) -> None:
        self.calls: list[dict] = []
        self.tasks: dict[str, dict] = {t["id"]: dict(t) for t in self.history_tasks}
        self.scheduled: dict[str, dict] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"task-new-{self._counter}"

    def delegations(self) -> list[dict]:
        return [c for c in self.calls if c["tool"] in ("delegate_to_task_agent", "dispatch_background_task")]

    def called(self, tool: str) -> bool:
        return any(c["tool"] == tool for c in self.calls)

    def _seed_block(self) -> str:
        blocks = []
        for task in self.seed_tasks:
            request = (task.get("request") or "")[:300]
            result = (task.get("result") or "")[:500]
            blocks.append(f"- task_id={task['id']} | [{task.get('label', '')}] task: {request}\n  result: {result}")
        return "\n".join(blocks)

    def _tools(self) -> list:
        world = self

        async def delegate_to_task_agent(request: str, task_id: str = "") -> str:
            """Run the capable task agent now, wait for its result, and return it for you to relay to
            the user. The task agent is powerful: it can control a computer, run shell commands and
            scripts, read/write files, drive a real web browser, and use many skills.

            Args:
                request: A complete, self-contained instruction for the task agent.
                task_id: Optional. Pass an existing task_id ONLY to continue that SAME task with its
                    prior context. Omit it to start a fresh, unrelated task.

            Returns:
                The result, prefixed with a `task_id=<id>` line. Reuse that task_id to continue later.
            """
            tid = task_id or world._new_id()
            existing = world.tasks.get(tid)
            result = f"Continued task: {request}" if (task_id and existing) else f"Completed: {request}"
            world.tasks[tid] = {
                "id": tid,
                "label": request[:60],
                "request": request,
                "result": result,
                "status": "done",
            }
            world.calls.append(
                {"tool": "delegate_to_task_agent", "request": request, "task_id": task_id, "minted": tid}
            )
            return f"task_id={tid}\n\n{result}"

        async def dispatch_background_task(request: str, label: str = "", task_id: str = "") -> str:
            """Start the task agent in the background and return immediately. The task agent is
            powerful: it can control a computer, run shell commands and scripts, read/write files,
            drive a real web browser, and use many skills.

            Args:
                request: A complete, self-contained instruction for the task agent.
                label: A short human-readable label for this task.
                task_id: Optional. Pass an existing task_id ONLY to continue that SAME task.
            """
            tid = task_id or world._new_id()
            world.tasks[tid] = {
                "id": tid,
                "label": label or request[:60],
                "request": request,
                "result": f"Completed: {request}",
                "status": "done",
            }
            world.calls.append(
                {"tool": "dispatch_background_task", "request": request, "task_id": task_id, "minted": tid}
            )
            return f"Started background task (task_id={tid}). I'll deliver the result here when it's ready."

        async def check_tasks() -> str:
            """List this conversation's tasks (in-flight and finished) with their task_id, label,
            status, and a short result summary."""
            world.calls.append({"tool": "check_tasks"})
            if not world.tasks:
                return "No tasks have been started in this conversation yet."
            return "\n".join(
                f"- task_id={t['id']} | {t['label']} | {t['status']} | {(t.get('result') or '')[:200]}"
                for t in world.tasks.values()
            )

        async def find_past_work(query: str = "", kind: str = "all", limit: int = 10) -> str:
            """Look up your full history of past tasks and scheduled jobs. Returns task_ids you can
            resume.

            Args:
                query: Optional text to filter by. Empty for the most recent.
                kind: "task", "job", or "all".
                limit: Max items per kind.
            """
            world.calls.append({"tool": "find_past_work", "query": query, "kind": kind})
            needle = query.lower()
            sections = []
            if kind in ("task", "all"):
                lines = [
                    f"- task_id={t['id']} | {t['label']} | {t['status']} | {(t.get('result') or '')[:200]}"
                    for t in world.tasks.values()
                    if not needle or needle in f"{t['label']} {t['request']} {t.get('result', '')}".lower()
                ]
                if lines:
                    sections.append("Tasks:\n" + "\n".join(lines))
            if kind in ("job", "all"):
                lines = [
                    f"- {j['job_name']} | {'OK' if j['success'] else 'FAIL'}"
                    for j in world.jobs
                    if not needle or needle in f"{j.get('job_name', '')} {j.get('error', '')}".lower()
                ]
                if lines:
                    sections.append("Jobs:\n" + "\n".join(lines))
            return "\n\n".join(sections) if sections else "No matching tasks or jobs found."

        async def episodic_search(query: str, days: int = 30) -> str:
            """Search past Synthia conversations by keyword. Use this to find context from previous
            sessions.

            Args:
                query: The search query.
                days: Number of days to search back.
            """
            world.calls.append({"tool": "episodic_search", "query": query})
            words = [w for w in query.lower().split() if len(w) > 3]
            hits = [c for c in world.conversations if any(w in c["summary"].lower() for w in words)]
            if not hits:
                return "No matching conversations found."
            return "\n".join(f"- id={c['id']} | {c['summary'][:300]}" for c in hits[:5])

        async def episodic_show(conversation_id: str) -> str:
            """Retrieve the full transcript of a past conversation by ID.

            Args:
                conversation_id: The conversation ID.
            """
            world.calls.append({"tool": "episodic_show", "conversation_id": conversation_id})
            for conv in world.conversations:
                if conv["id"] == conversation_id:
                    return conv.get("transcript", conv["summary"])
            return "No conversation found."

        async def add_job(name: str, start_date: str, seconds: float, task: str, silent: bool = False) -> str:
            """Add a new recurring scheduled job that triggers a task repeatedly at an interval.

            Args:
                name: Unique job name.
                start_date: When the job should first run (ISO datetime).
                seconds: Interval between runs, in seconds.
                task: The task instruction to run on each trigger.
                silent: Whether to suppress completion notifications.
            """
            world.scheduled[name] = {"name": name, "seconds": seconds, "task": task}
            world.calls.append({"tool": "add_job", "name": name, "task": task})
            return f"Job '{name}' scheduled."

        async def list_jobs() -> str:
            """List all currently scheduled jobs with their names, intervals, and tasks."""
            world.calls.append({"tool": "list_jobs"})
            if not world.scheduled:
                return "No scheduled jobs found."
            return "\n".join(
                f"- {j['name']} | every {j['seconds']}s | {j['task'][:60]}" for j in world.scheduled.values()
            )

        async def delete_job(name: str) -> str:
            """Delete a scheduled job by its name.

            Args:
                name: The name of the job to delete.
            """
            world.calls.append({"tool": "delete_job", "name": name})
            if name in world.scheduled:
                del world.scheduled[name]
                return f"Job '{name}' deleted successfully."
            return f"No job named '{name}'."

        async def search_memories(query: str) -> str:
            """Search stored memories about the user.

            Args:
                query: The search query.
            """
            world.calls.append({"tool": "search_memories", "query": query})
            words = [w for w in query.lower().split() if len(w) > 2]
            hits = [m for m in world.memories if any(w in m["content"].lower() for w in words)] or world.memories
            if not hits:
                return "No memories found."
            return "\n".join(f"- id={m['id']} | {m['content']}" for m in hits[:5])

        async def add_memory(content: str) -> str:
            """Save a durable memory about the user.

            Args:
                content: The fact to remember.
            """
            mid = f"mem-{len(world.memories) + 1}"
            world.memories.append({"id": mid, "content": content})
            world.calls.append({"tool": "add_memory", "content": content})
            return f"Saved memory {mid}."

        return [
            delegate_to_task_agent,
            dispatch_background_task,
            check_tasks,
            find_past_work,
            episodic_search,
            episodic_show,
            add_job,
            list_jobs,
            delete_job,
            search_memories,
            add_memory,
        ]

    async def front_agent(self) -> Agent:
        instruction = self.instruction or build_front_instruction(self._seed_block())
        return await Agent.create(
            tools=self._tools(),
            model=self.model,
            system_prompt=instruction,
            include_builtins=False,
            name="synthia",
            prompt_thread_hint=False,
        )


def _sid() -> str:
    return uuid.uuid4().hex


async def _run(world: StubWorld, agent: Agent, message: str) -> str:
    result = await agent.run_for_result(objective=message, session_id=_sid_for(agent))
    return (result.result if result else "") or ""


_AGENT_SESSIONS: dict[int, str] = {}


def _sid_for(agent: Agent) -> str:
    return _AGENT_SESSIONS.setdefault(id(agent), _sid())


async def run_eval(scenario, runs: int = EVAL_RUNS) -> list[EvalResult]:
    async def _timed() -> EvalResult:
        start = perf_counter()
        try:
            passed, detail = await scenario()
        except Exception as error:
            return EvalResult(False, perf_counter() - start, f"error: {error}")
        return EvalResult(bool(passed), perf_counter() - start, detail)

    return list(await asyncio.gather(*[_timed() for _ in range(runs)]))


def _rate(results: list[EvalResult]) -> float:
    return sum(r.passed for r in results) / len(results)


def _report(name: str, results: list[EvalResult]) -> str:
    avg = sum(r.duration_s for r in results) / len(results)
    lines = [f"{name}: pass={sum(r.passed for r in results)}/{len(results)} avg={avg:.1f}s"]
    for i, r in enumerate(results):
        lines.append(f"  run{i}: {'PASS' if r.passed else 'FAIL'} {r.duration_s:.1f}s | {r.detail}")
    return "\n".join(lines)


def _assert(name: str, results: list[EvalResult], *, min_rate: float, max_seconds: float) -> None:
    assert max(r.duration_s for r in results) < max_seconds, _report(name, results)
    assert _rate(results) >= min_rate, _report(name, results)


# --- Passing evals ----------------------------------------------------------


async def test_eval_recall_recent_task() -> None:
    async def scenario():
        world = StubWorld(seed_tasks=[KAVITA])
        agent = await world.front_agent()
        try:
            text = await _run(world, agent, "In Kavita, how many books did I rate? Answer with the number.")
            return ("120" in text and not world.delegations()), text[:80]
        finally:
            await agent.disconnect()

    _assert("recall_recent_task", await run_eval(scenario), min_rate=0.75, max_seconds=45)


async def test_eval_start_new_task() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            text = await _run(
                world, agent, "Check the latest issues of my magazine subscriptions and tell me which I'm behind on."
            )
            return bool(world.delegations()), f"delegations={len(world.delegations())} | {text[:60]}"
        finally:
            await agent.disconnect()

    _assert("start_new_task", await run_eval(scenario), min_rate=0.75, max_seconds=50)


async def test_eval_direct_answer_no_delegation() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            text = await _run(world, agent, "Hey! What's your name?")
            return (not world.delegations() and "synthia" in text.lower()), text[:60]
        finally:
            await agent.disconnect()

    _assert("direct_answer", await run_eval(scenario), min_rate=0.75, max_seconds=45)


async def test_eval_search_past_conversations() -> None:
    async def scenario():
        world = StubWorld(seed_tasks=[KAVITA], conversations=[GARMIN_CONV])
        agent = await world.front_agent()
        try:
            text = await _run(world, agent, "What did we decide to do about my Garmin watch's sleep tracking problem?")
            return world.called("episodic_search"), f"searched={world.called('episodic_search')} | {text[:60]}"
        finally:
            await agent.disconnect()

    _assert("search_past_conversations", await run_eval(scenario), min_rate=0.75, max_seconds=55)


async def test_eval_manage_scheduled_jobs() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            await _run(
                world,
                agent,
                "Schedule a recurring job called 'magazine-check' that checks my magazines every morning.",
            )
            await _run(world, agent, "What scheduled jobs do I have right now?")
            await _run(world, agent, "Great, now delete the magazine-check job.")
            added = world.called("add_job")
            listed = world.called("list_jobs")
            deleted = world.called("delete_job")
            ok = added and listed and deleted and not world.scheduled
            return ok, f"add={added} list={listed} delete={deleted} remaining={list(world.scheduled)}"
        finally:
            await agent.disconnect()

    _assert("manage_scheduled_jobs", await run_eval(scenario), min_rate=0.75, max_seconds=90)


async def test_eval_recall_memory() -> None:
    async def scenario():
        world = StubWorld(memories=[{"id": "m1", "content": "The user's favorite tea is genmaicha."}])
        agent = await world.front_agent()
        try:
            text = await _run(world, agent, "Remind me — what's my favorite kind of tea?")
            return ("genmaicha" in text.lower()), f"searched={world.called('search_memories')} | {text[:60]}"
        finally:
            await agent.disconnect()

    _assert("recall_memory", await run_eval(scenario), min_rate=0.75, max_seconds=45)


async def test_eval_resume_task_new_session() -> None:
    async def scenario():
        world = StubWorld(seed_tasks=[MAGAZINE], history_tasks=[MAGAZINE])
        agent = await world.front_agent()
        try:
            await _run(world, agent, "Go back to the magazine check we did and also add The Economist to it.")
            resumed = any(d["task_id"] == MAGAZINE["id"] for d in world.delegations())
            return resumed, f"delegations={[d['task_id'] for d in world.delegations()]}"
        finally:
            await agent.disconnect()

    _assert("resume_new_session", await run_eval(scenario), min_rate=0.75, max_seconds=70)


async def test_eval_resume_correct_task_among_many() -> None:
    async def scenario():
        history = [MAGAZINE, KAVITA, VACUUM, RUG, TV]
        world = StubWorld(seed_tasks=history, history_tasks=history)
        agent = await world.front_agent()
        try:
            await _run(world, agent, "Pick up the robot vacuum comparison again and add the Roborock S8 to it.")
            resumed = any(d["task_id"] == VACUUM["id"] for d in world.delegations())
            return resumed, f"delegations={[d['task_id'] for d in world.delegations()]}"
        finally:
            await agent.disconnect()

    _assert("resume_among_many", await run_eval(scenario), min_rate=0.75, max_seconds=70)


async def test_eval_delegate_local_system_task() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            text = await _run(world, agent, "Please back up my ~/photos folder to an external drive right now.")
            return bool(world.delegations()), f"delegations={len(world.delegations())} | {text[:70]}"
        finally:
            await agent.disconnect()

    _assert("delegate_local_system_task", await run_eval(scenario), min_rate=0.75, max_seconds=50)


async def test_eval_continue_task_same_session() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            await _run(world, agent, "Check my magazine issues and tell me which are current.")
            await _run(world, agent, "Great — now also add Wired and New Scientist to that same check.")
            delegations = world.delegations()
            if len(delegations) < 2:
                return False, f"only {len(delegations)} delegations"
            first_id = delegations[0]["minted"]
            reused = any(d["task_id"] == first_id for d in delegations[1:])
            return reused, f"first={first_id} reused={reused}"
        finally:
            await agent.disconnect()

    _assert("continue_same_session", await run_eval(scenario), min_rate=0.75, max_seconds=75)


# --- Stretch evals (the agent is not expected to do these reliably) ---------
# Keep stretch evals at ~30% of the suite. When you fix one so it passes reliably and promote it,
# add a new harder one here to hold the ratio.


@pytest.mark.xfail(reason="stretch: fan a single message out into 3 separate task delegations", strict=False)
async def test_eval_parallel_multi_task_dispatch() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            await _run(
                world,
                agent,
                "Three separate jobs please: (1) check my magazine issues, (2) back up my ~/photos "
                "folder, and (3) look up tomorrow's weather in Tokyo.",
            )
            count = len(world.delegations())
            return count >= 3, f"delegations={count}"
        finally:
            await agent.disconnect()

    _assert("parallel_multi_task", await run_eval(scenario), min_rate=0.75, max_seconds=75)


@pytest.mark.xfail(reason="stretch: resume a task after an unrelated turn interrupts the conversation", strict=False)
async def test_eval_resume_after_interruption() -> None:
    async def scenario():
        world = StubWorld(memories=[{"id": "m1", "content": "The user's favorite tea is genmaicha."}])
        agent = await world.front_agent()
        try:
            await _run(world, agent, "Check my magazine issues and tell me which are current.")
            first = world.delegations()[0]["minted"] if world.delegations() else None
            await _run(world, agent, "By the way, what's my favorite tea again?")
            await _run(world, agent, "Cool. Now go back to that magazine check and also add Wired to it.")
            resumed = first is not None and any(d["task_id"] == first for d in world.delegations()[1:])
            return resumed, f"first={first} ids={[d['task_id'] for d in world.delegations()]}"
        finally:
            await agent.disconnect()

    _assert("resume_after_interruption", await run_eval(scenario), min_rate=0.75, max_seconds=90)


@pytest.mark.xfail(reason="stretch: pick the right task when two share a topic but differ in intent", strict=False)
async def test_eval_disambiguate_same_topic_task() -> None:
    async def scenario():
        history = [MAGAZINE, MAGAZINE_CANCEL]
        world = StubWorld(seed_tasks=history, history_tasks=history)
        agent = await world.front_agent()
        try:
            await _run(world, agent, "Go finish cancelling that magazine subscription for me.")
            resumed = any(d["task_id"] == MAGAZINE_CANCEL["id"] for d in world.delegations())
            return resumed, f"ids={[d['task_id'] for d in world.delegations()]}"
        finally:
            await agent.disconnect()

    _assert("disambiguate_same_topic", await run_eval(scenario), min_rate=0.75, max_seconds=60)


@pytest.mark.xfail(
    reason="stretch: infer which part is quick (sync) vs long (background) without explicit cues",
    strict=False,
)
async def test_eval_mixed_sync_and_background() -> None:
    async def scenario():
        world = StubWorld()
        agent = await world.front_agent()
        try:
            await _run(
                world,
                agent,
                "Tell me which of my magazine issues are current, and also put together a thorough "
                "multi-week competitive teardown of the top 20 espresso machines on the market.",
            )
            both = world.called("delegate_to_task_agent") and world.called("dispatch_background_task")
            return both, f"sync={world.called('delegate_to_task_agent')} bg={world.called('dispatch_background_task')}"
        finally:
            await agent.disconnect()

    _assert("mixed_sync_and_background", await run_eval(scenario), min_rate=0.75, max_seconds=70)
