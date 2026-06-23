# Front-agent evaluation suite (`test_eval_front_agent.py`)

How and why these evals are written, for anyone running or extending them.

## What it evaluates

The capabilities of the **front agent** (the cheap `gpt-5.4-nano` agent that talks to the user and
routes work) — recalling recent tasks, starting/resuming tasks, searching past conversations,
managing scheduled jobs and memories, answering directly vs delegating, etc.

## The core idea: real agent, stubbed tools

Each eval runs the **real front agent** — the real model (`FRONT_MODEL`) and the real production
system prompt (`build_front_instruction` from `synthia/agents/agent.py`) — but wires it to **stub
tools** instead of the real task agent / databases. The stubs live in `StubWorld`.

Why stub the tools instead of running the real task agent:

- **We're testing routing, not task execution.** The interesting question is *what the front agent
  decides to do* — which tool it calls, with what `task_id`, whether it delegates or answers
  directly. The stubs record every call in `world.calls`, so assertions are about decisions, not
  about a heavy Sonnet task agent's output.
- **Deterministic, fast, free.** No Sonnet calls, no Postgres, no network beyond the one nano call
  per turn. An eval run is seconds, not minutes.
- This is the one place we deliberately use stubs (the repo's default is "no mocks") — it's what
  makes evaluating the front agent in isolation possible.

`StubWorld` is seedable state:

- `seed_tasks` → rendered into the prompt's "recent activity" block (mirrors `_recent_tasks_block`).
- `history_tasks` → what `find_past_work` / `check_tasks` can return.
- `conversations` → what `episodic_search` / `episodic_show` return.
- `memories` → what `search_memories` returns.
- `scheduled` → mutated by the `add_job` / `list_jobs` / `delete_job` stubs.

## Anatomy of an eval

```python
async def test_eval_X():
    async def scenario():
        world = StubWorld(seed_tasks=[...])      # arrange state
        agent = await world.front_agent()        # real front agent on stub tools
        try:
            text = await _run(world, agent, "user message")   # drive a turn (or several)
            return <bool pass>, "<detail for the report>"     # assert on world.calls / text
        finally:
            await agent.disconnect()
    _assert("X", await run_eval(scenario), min_rate=0.75, max_seconds=N)
```

- **Every eval runs `EVAL_RUNS` times (default 4), concurrently** — small models are
  non-deterministic, so a single run proves nothing. `_assert` requires a **pass rate** (default
  >=3/4) *and* a **timing ceiling** (`max_seconds`). `_report` prints per-run PASS/FAIL + duration +
  detail on failure.
- **Multi-turn** scenarios reuse the same `agent` across `_run` calls (same session), so the front
  agent remembers prior turns. **New-session** scenarios build a fresh `StubWorld` + agent.

## Passing vs stretch evals

- **Passing** evals assert `min_rate=0.75`: capabilities the agent handles reliably.
- **Stretch** evals are marked `@pytest.mark.xfail(..., strict=False)`: capabilities the agent
  *cannot* do reliably. `strict=False` means both an expected failure (XFAIL) and an occasional lucky
  pass (XPASS) keep the suite green. They document known limitations without making CI flaky.
- The intent is a mix: some pass, some stretch. When a stretch eval is *fixed* (see below) and starts
  passing reliably, promote it — remove the `xfail` and move it to the passing section.
- **Keep stretch evals at ~30% of the suite.** This agent is capable, so genuinely-hard cases take
  effort to find — the reliable ones probe edges like fanning one message into several delegations,
  resuming a task after an unrelated turn interrupts, disambiguating two same-topic tasks by intent,
  or inferring sync-vs-background mode without explicit cues. When you fix and promote a stretch eval,
  add a new harder one to hold the ratio. Stretch evals swing between XFAIL and XPASS run to run —
  that is expected; `strict=False` keeps both green. Avoid "stretch" evals that pass on every run
  (e.g. tasks with obvious lexical cues) — they belong in the passing set.

## Tuning knobs (A/B prompts and models)

The suite is built to compare configurations without touching scenarios:

- `EVAL_FRONT_MODEL` (env `EVAL_FRONT_MODEL`) — evaluate a different model tier.
- `EVAL_INSTRUCTION` — set a string to override the front system prompt wholesale.
- `EVAL_RUNS` (env) — change the repetition count.

## Keeping stubs faithful (important)

The eval is only meaningful if the front agent sees the **same signals** in the eval as in
production. Two things must be mirrored from the real code:

1. **Stub tool docstrings** must match the real tool docstrings (`delegate_to_task_agent`,
   `dispatch_background_task`, `check_tasks`, `find_past_work`, `episodic_*`, `add_job`/`list_jobs`/
   `delete_job`, `search_memories`/`add_memory`) — the model routes off these schemas. The real ones
   live in `synthia/service/task.py` and the tool modules.
2. **The seed format** (`StubWorld._seed_block`) must match `TaskService._recent_tasks_block` — e.g.
   each entry leading with `task_id=<id>`.

When you change a real tool's docstring, the system prompt, or the seed format, update the mirror
here too, or the eval drifts from reality.

## How findings feed back

These evals are a debugging tool, not just a gate. Run them, read the failure details, and fix the
*agent* (prompt / tool descriptions / seed), not the test. Examples this suite surfaced and drove:

- The agent **over-delegated recall questions** once `task_id`s were added to the seed → split the
  prompt into "do more work on a task" (delegate with id) vs "answer a fact from its result"
  (reply directly).
- The agent **refused local-system tasks** ("I can't access your computer") → the
  `delegate_to_task_agent` description now states the task agent can control a computer, run scripts,
  drive a browser, etc., plus "never tell the user you can't — delegate it."
- The agent **didn't reuse a `task_id` from a prior turn** → the prompt now says the returned
  `task_id=<id>` line is what to pass back for follow-ups, with `check_tasks()` as a fallback.

## Running

```bash
uv run pytest tests/test_eval_front_agent.py -p no:testmon -o addopts="" -m eval
```

`conftest.py` loads `.env`, so the provider key is picked up automatically. The model is the single
source of truth in `synthia/agents/agent.py` (`FRONT_MODEL_SPEC`); the suite is gated by
`@pytest.mark.eval` + a `skipif` on that model's provider key (derived via `required_api_key`), so it
is opt-in and excluded from the default `make test` run.
