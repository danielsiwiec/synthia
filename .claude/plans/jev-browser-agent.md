# Plan: Jev-driven browser agent for the front/voice model

Status: **implemented 2026-09-19** (uncommitted on `main`, alongside the in-flight voice work).
Spec: `specs/agent.md` → "Browser agent". Code: `synthia/agents/browser/`. Tests: `tests/test_browser.py`.
Deviations from the plan below: the action/target decision uses per-action target questions
(`click_target` / `type_target` / `select_target`) in one fan-out call; page text is a structured
serialization (headings, list items, table rows) rather than flat innerText; the state carries the
values themselves (secret-looking keys masked) plus a code-computed `values_now_visible_in_page_text`
signal so Jev can judge `goal_met` literally. The magazines skill was rewritten onto the new tools
and its batch check script onto Playwright-over-CDP.

## 1. What Jev actually is (findings)

- **Jev is not a browser agent.** It is TypeSafe's "System One" decision model: one HTTP
  call (`POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer $TYPESAFE_API_KEY`)
  takes `state` (string / JSON object / array, text only) plus a map of named typed
  questions and returns typed answers, all questions evaluated in parallel in ~300 ms.
  - Question types: `noul` (yes/no → probability 0–1), `choice` (pick one of ≤255 options →
    choice + probability distribution + confidence), `score` (2–10 ordered levels → score +
    distribution + confidence).
  - Model ids: `jev-latest` (alias → `jev-1.13.0`), `jev-preview`. Limits: 64k tokens per
    request, 32k for state + longest question; 1,200 req/min, 250k tok/s. Pricing:
    **$0.042 per 1M input tokens, output free.**
  - Python SDK: `typesafe-sdk` (`AsyncTypeSafeClient(api_key, model, retry=RetryPolicy,
    timeout, base_url)`, `await client.system_one(state, questions)`; `Noul`, `Choice`,
    `Score` helpers; reads `TYPESAFE_API_KEY`). Built on httpx.
  - Jev **never generates text**. Any string the browser needs (a search query, a form
    value) must come from the caller or a separate small LLM.
  - Known jaggedness (jev-1.13): literal reading of instructions, weak at counting/dates,
    large irrelevant state degrades accuracy, **not adversarially trained** (page text can
    steer it), no guarantee P(yes)+P(no)=1. Mitigations: prune state in code, precise
    criteria, keep thresholds per-primitive, gate irreversible actions in code.
- **The "browser" part is a runtime layered on Jev**, all third-party. TypeSafe's official
  "agent skill" is documentation only. Surveyed runtimes:

  | Runtime | Lang | Browser attach | Notes |
  | --- | --- | --- | --- |
  | `browser-use/jev-ultrafast` | Python 3.12 | Browser Harness only (local Chrome + `chrome://inspect` toggle, or Browser Use cloud); no plain CDP URL | Best loop design (indexed action space, one Jev call per step, small text LLM for TYPE_TEXT); not on PyPI; tightly coupled to browser-harness |
  | `forvela/jev-agent-browser` | Node | `--attach --cdp 9222` over Vercel `agent-browser` (what Synthia already uses) | CLI/JSONL, parent supplies values, structured handoff on stop; MIT |
  | `Ying-Kai-Liao/jev-browser` (npm `jev-browser`) | Node | Launches its own Playwright Chromium (`JEV_BROWSER_HEADED`, `JEV_BROWSER_PROFILE`); no CDP | MCP server: `browser_do/check/choose/snapshot/act/screenshot`; Claude plans, Jev decides |
  | `MahmoudAdelbghany/jev-browser` | Node | Headless Playwright only | MCP `jev_goal/step/observe/act/ask`; benchmarks vs Playwright MCP (1.5× faster, 1.6× cheaper) |
  | `jkudish/jev-browser` | Node | Own Playwright, headed via env | MCP/CLI/lib; goal + stuck classifiers at 0.85 |

  None is Python **and** able to attach to Synthia's existing headed host Chrome over CDP.

## 2. How it fits Synthia today

- Browser access today is task-agent only: `agent-browser` CLI via the `abr` shell wrapper
  (`run_bash`), attached over CDP to the resident **host Chrome on mini**
  (`misc/services/chrome-cdp.sh`, `--remote-debugging-port=9222`), reached from the
  container at `http://192.168.65.254:9222` (`ABR_CDP_HTTP`). That Chrome is already a real,
  headed window with persistent logins, so "headed" is satisfied by reusing it.
- CDP gotcha (do not relitigate): use the gateway **IP**, not `host.docker.internal`, and do
  **not** send a `Host: localhost` header. Playwright then rewrites Chrome's `ws://localhost`
  correctly.
- The front agent has no browser tools; it delegates. In voice mode a blocking tool silences
  the call, so long tools must run as background tasks and return through
  `TaskService._deliver_via_front` (which pushes text into the live session).
- The `run_bash` path has a known hang class (agent-browser daemon holds stdout → 600 s
  timeout on first call). Anything we build should **not** shell out per step.
- Infra already present: Node 22 + chromium in the image, `synthia/agents/mcp.py` supports
  stdio/http MCP servers, `ModelSpec`/`_MODEL_SPECS` single home for model pricing,
  `record_delegated_cost` for rolling sub-work cost into the front turn, pubsub messages
  `ProgressNotification` / `OutgoingImage` for progress and screenshots, `tasks` table for
  background work.

## 3. Recommendation

Build a small **in-process Python browser agent** (`synthia/agents/browser/`) whose decision
loop is Jev (via `typesafe-sdk`) and whose eyes/hands are **Playwright-Python attached over
CDP to the existing host Chrome**. Expose it as one front-agent tool (`browse`) and a
fine-grained tool family on the task agent.

Why this over adopting a runtime:
- Python + async + in-process: plugs into pubsub (progress, screenshots), cost tracking,
  telemetry spans, cancellation/stop, and the voice background-delivery path with no
  subprocess or daemon.
- Reuses the headed host Chrome and its sessions (Cloudflare/login pass-through) exactly
  like `abr`; `playwright.chromium.connect_over_cdp(ABR_CDP_HTTP)` needs no browser
  download (only the driver in the wheel).
- The loop itself is ~300 lines; jev-ultrafast's design is the template
  (indexed action space, one fan-out Jev call per step, code-owned verification).

Fallback / spike option (B): run `forvela/jev-agent-browser --attach --cdp` as a stdio
subprocess with JSONL parsing. Fastest way to see Jev drive our Chrome (an afternoon), but
it inherits the agent-browser daemon/pipe risk and gives no per-step hooks. Use it only as a
throwaway feasibility check if the user wants a demo before committing.

## 4. Design

### 4.1 Module layout
```
synthia/agents/browser/
  jev.py        # AsyncTypeSafeClient wrapper: batched questions, retry, usage → cost, spans
  page.py       # Playwright CDP session: connect, own tab, observe(), act(), screenshot()
  actions.py    # indexed action space: element table + action/target/value enums (pure code)
  loop.py       # observe → decide → act → verify loop, budgets, stuck detection, escalation
  tools.py      # ADK function tools for task agent + front agent (text and voice variants)
```
All internals `_`-prefixed; no comments/docstrings except tool docstrings (ADK reads them).

### 4.2 Observation (`page.observe`)
- Snapshot via CDP/Playwright: visible, interactive elements (links, buttons, inputs,
  selects, textareas, role=button/tab/menuitem, contenteditable) with a stable index,
  role, accessible name/label, value, placeholder, `href` host, in-viewport flag.
- Prune in code before Jev sees it: keep visible-in-viewport first, then rank by lexical
  overlap with the goal; cap at ~80 candidates (Choice max 255; accuracy drops with
  distractors). Include compact page context: url, title, first ~1.5k chars of main text,
  any visible error/alert text, scroll position.
- Stay under ~8k tokens of state per step.

### 4.3 Decision (one Jev request per step, fan-out)
- `action`: Choice over `click | type | select | scroll_down | scroll_up | back | wait |
  done | blocked`, each with a one-line criterion.
- `target`: Choice over element indices (criteria = the pruned element descriptions).
- `value`: Choice over the caller-supplied `values` keys (only relevant when action is
  type/select). Jev cannot invent text, so `browse(goal, values={"query": "…"})` is the
  contract; missing value → status `needs_input`.
- `goal_met`: Noul "the goal is fully achieved on this page".
- `stuck`: Noul "no available action makes progress".
- `irreversible`: Noul "the chosen action submits a payment, sends a message, or deletes
  something". If p > 0.5 and `allow_irreversible=False` → stop with `needs_confirmation`.
- Confidence routing: `target` confidence < 0.35 for two consecutive steps → `needs_agent`.

### 4.4 Act + verify
- Execute via Playwright on the element handle resolved from the index (re-resolve after
  every observe; validate it is still attached and visible).
- After acting, wait for network-idle-ish settle (≤1 s), re-observe, hash the observation;
  three identical hashes → stuck. Keep a short `history` (last 5 actions) in state so Jev
  sees what was tried.
- Budgets: `max_steps` (default 25), wall clock (default 90 s front / 240 s task agent),
  per-call Jev timeout 5 s with SDK retry.

### 4.5 Result
`BrowseResult` (pydantic): `status` ∈ `done | needs_input | needs_confirmation |
needs_agent | blocked | timeout | error`, `url`, `title`, `summary` (main text, capped),
`steps`, `jev_tokens`, `cost_usd`, `screenshot_path`. Serialized to the tool string for
the planner; screenshot published as an `OutgoingImage` (text chat only).

### 4.6 Tool surface
- **Task agent** (fine-grained, for takeover and for skills): `browser_do(goal, url="",
  values={}, max_steps=25, allow_irreversible=False)`, `browser_observe()`,
  `browser_act(action, element, value="")`, `browser_check(question)` (Noul over the page),
  `browser_screenshot()`. `abr` stays available for downloads/`eval`/edge cases.
- **Front agent (text)**: `browse(goal, url="", values={})` — synchronous, short budget
  (≤90 s), returns `BrowseResult`. Prompt guidance: use for single-site, single-goal jobs
  (look up a JS-rendered/logged-in page, fill a known form, check a status); multi-site
  research or file work still goes to the task agent.
- **Front agent (voice)**: same tool name, but implemented like `delegate_in_voice`: creates
  a `tasks` row (`background=true`, label "Browse: …"), runs the loop in a background
  asyncio task under the existing semaphore, and delivers through `_deliver_via_front` so
  the live model narrates the result. Returns immediately with the task_id.
- On `needs_agent`/`needs_input` the front agent decides: re-call `browse` with values or a
  narrower goal, or dispatch the task agent (which has the fine-grained tools and `abr`).

### 4.7 Browser session management
- One Playwright connection per process (lazy, reconnect on failure); one **tab per browse
  run** opened in Chrome's default context, closed on completion unless `keep_open=True`
  (task agent only). Coexists with `abr` sessions.
- Global concurrency limit `BROWSER_MAX_CONCURRENT` (default 2) to avoid fighting over the
  single Chrome; per-thread at most one run at a time.

### 4.8 Cost, telemetry, progress
- Add `JEV_MODEL_SPEC = ModelSpec("jev-latest", input_cost_per_m=0.042, output_cost_per_m=0)`
  next to the other specs. Sum `usage.input_tokens` per run; record with
  `record_delegated_cost` so the front turn's `cost_usd` includes browsing; emit spans
  (`browser_run`, `browser_step`, `jev_call`) and a Prometheus counter for Jev tokens.
- Every 3 steps publish `ProgressNotification("Browsing <host>: <last action>")` so the
  SSE `progress` event shows activity in text chat.

### 4.9 Config / env
- `TYPESAFE_API_KEY` (required; when unset the tools are not registered and prompts omit
  them, same pattern as voice's `GEMINI_API_KEY` gate).
- `BROWSER_CDP_HTTP` (default = `ABR_CDP_HTTP` = `http://192.168.65.254:9222`).
- `JEV_MODEL` (`jev-latest`), `BROWSER_MAX_STEPS` (25), `BROWSER_TIMEOUT_S` (90),
  `BROWSER_MAX_CONCURRENT` (2), `BROWSER_MAX_CANDIDATES` (80).
- Deps: `uv add typesafe-sdk playwright`. No `playwright install` needed (CDP attach).

## 5. Spec deltas (write these first)

- `specs/agent.md`
  - New section **"Browser agent"**: Jev as decision model, the loop (observe/decide/act/
    verify), statuses, budgets, escalation, irreversible gate, session/tab rules,
    availability gate on `TYPESAFE_API_KEY`.
  - **Front agent → Tools**: add `browse`; **Voice mode → Tools in voice mode**: `browse`
    runs as a background task delivered into the live session.
  - **Task agent → Tool inventory**: add the `browser_*` family; reword "Web access
    escalates" to: `fetch_url` → `browser_do` → `abr` (takeover/downloads).
  - **Model**: add the Jev model spec and pricing (single home).
  - **Runtime knobs**: the env vars above. **Cost tracking**: Jev tokens roll into the
    originating turn.
- `specs/state.md` → `tasks`: note that voice-mode browse runs create background task rows
  (no schema change).
- `specs/api.md`: no new routes; `progress` and `image` events gain a new producer (one-line
  mention). `toc.md` unchanged.
- Reconcile: remove the assumption that browsing is task-agent-only wherever stated.

## 6. Implementation steps

0. **Prereqs** (user): create a key at https://console.typesafe.ai/keys, add
   `TYPESAFE_API_KEY` to `.env` on mini and locally. Verify from the container:
   `curl -s http://192.168.65.254:9222/json/version`.
1. Spec deltas per §5; reconcile; `/spec-check agent`.
2. `uv add typesafe-sdk playwright`; `jev.py` wrapper + `actions.py` (pure code) with smoke
   tests.
3. `page.py`: CDP connect, observe, act, screenshot; test against a local static fixture
   page served by an in-test HTTP server, driven by a locally launched Chromium when
   available (skip otherwise, like the voice tests skip without a key).
4. `loop.py` + `BrowseResult`; eval test (marker `eval`, skipif no key) on a TodoMVC-style
   fixture: "add an item" with `values={"item": "buy milk"}` → `done` in ≤ 6 steps.
5. `tools.py`: task-agent tools first (wired in `main.py` next to MCP toolsets), then the
   front `browse` (text sync / voice background in `TaskService`), prompt updates in
   `agent.py` (`SYSTEM_PROMPT`, `FRONT_SYSTEM_PROMPT`, `VOICE_INSTRUCTION_ADDENDUM`).
6. Cost/telemetry/progress/screenshot wiring; model spec.
7. `make check`; smoke tests without xdist; full suite with `-n auto`.
8. Deploy to mini (`make up`), try: "check whether my Goodreads shelf has X",
   "search the Arr UI for Y", one form fill; compare wall time and cost against the `abr`
   path in Grafana; tune pruning and thresholds.
9. Update the `.claude/skills/*` / `skills/publish-report` wording that still says browser
   work is `abr`-only.

Rough size: steps 1–4 ≈ 1 day, 5–6 ≈ 0.5 day, 7–9 ≈ 0.5 day of iteration.

## 7. Risks and open questions

- **Values contract.** Jev cannot write text. Phase 1 requires the planner to pass `values`.
  Phase 2 option: let the loop ask the configured cheap model (`FRONT_MODEL_SPEC`) for a
  value when Jev picks `type` and no value fits — costs one LLM call, keeps Jev in charge.
- **Prompt injection.** Jev is not adversarially trained; page text can steer `action`.
  The irreversible gate plus a code allowlist (never `type` into password fields, never
  navigate off the starting registrable domain unless the goal names another host) is the
  mitigation. Decide whether cross-domain navigation needs an explicit flag.
- **Shared Chrome.** Two runs plus an `abr` session on one Chrome can interfere; the
  per-tab isolation and `BROWSER_MAX_CONCURRENT` are the guardrails. If it becomes a
  problem, give the browser agent its own Chrome profile/service on mini.
- **Playwright driver in the image.** The wheel bundles a Node driver; Node 22 is already
  present. Pin the version; watch image size.
- **Voice latency.** Even a 20 s browse is long in a call; the background path means the
  model must say "on it" and continue. Consider a spoken progress ping after ~15 s.
- **Front vs task budget.** 90 s sync in text chat blocks the thread; if it feels slow,
  switch text mode to background too and rely on `result` delivery.
