# Agent Architecture

Synthia runs on the **Google ADK** (Agent Development Kit). Models are invoked through
ADK's LiteLlm adapter, so the same code path serves Anthropic, Gemini, and OpenAI models.
Data-model and API names (thread, task, session, SSE events) are defined in `state.md` and
`api.md`.

## Framework & execution model

- **Agent class:** ADK `LlmAgent`. **Runner:** ADK `Runner`, driving execution and
  streaming events in `StreamingMode.SSE`. **App name:** `synthia`. **User id:** `default`.
- **Sessions:** ADK `DatabaseSessionService` over Postgres (`postgresql+psycopg://`);
  `InMemorySessionService` in dev. Session/event tables are ADK-owned (see `state.md`).
- A session id equals the `thread_id` (chat) or `task-<uuid>` (task). The agent instance is
  cached per thread and reused across turns within that thread.
- **Where it runs:** in-process inside the FastAPI app — not sandboxed. The task agent has
  real shell access via `run_bash` and read/write access to the host filesystem. Treat this
  as a trust boundary.

## Two-tier agent design

Synthia separates a cheap, user-facing **front agent** from a powerful **task agent**.

### Front agent
- **Role:** talks to the user on a chat thread, answers directly when it can, and decides
  what to delegate. It hides internal mechanics from the user (no mention of sessions,
  delegation, context, etc.).
- **Tools:** no builtins. It manages memory, scheduling, and projects directly, and routes
  heavy work to the task agent via three delegation tools:
  - `delegate_to_task_agent(request, task_id="")` — **synchronous**: runs the task agent
    now and blocks until the result is ready (user is waiting). Returns the result prefixed
    with its `task_id`.
  - `dispatch_background_task(request, label="", task_id="")` — **asynchronous**: starts the
    task agent in the background and returns immediately; the result is delivered into the
    chat when ready. Bounded by `FRONT_MAX_CONCURRENT_TASKS` (default 3).
  - `check_tasks(task_id="")` — list this thread's tasks with status. For a task that is
    still running the line shall include live detail derived from its persisted session
    events: how long it has run, and either the tool call currently in flight (name,
    argument excerpt, seconds since it started) or the last completed step. With a
    `task_id` the tool shall instead return that task's full execution trail — every tool
    call with its argument and result excerpts, model text, and relative timestamps —
    capped to the most recent entries, so the caller can review what the task agent did or
    is doing.
- **Other front-only tools:** `find_past_work`, `consult_persona`, `episodic_search`,
  `episodic_show`, the memory tools, the scheduler tools, and the thread-level project tools
  (`create_project`, `select_project`, `add_project_section`, `attach_project_media`).
- **Images:** the front agent has no image tools and cannot render a picture itself. When the
  user asks to see something (a cover, a screenshot, a chart, a photo), the front agent shall
  delegate to the task agent, which shows it inline in the chat via `send_image` /
  `render_diagram` (see "Tool inventory"); it shall never tell the user it cannot display
  images. This applies in voice mode too: the image appears in the chat view of the thread the
  call is on, and the model says so rather than reading out a path or URL.
- **`browse(goal, url="", values={})`** (only while the browser agent is available): runs the
  Jev-driven browser loop (see "Browser agent") on a single site for a single goal and
  returns its structured result. In text mode it is synchronous with the front budget; in
  voice mode it behaves like a background dispatch (see "Tools in voice mode").
- When `FRONT_AGENT_ENABLED=0`, the task agent handles everything directly.

### Voice mode (front agent, live)
The front agent can also be driven as a **live voice agent** on a chat thread. Voice mode is a
transport and model variant of the front agent, not a separate agent: it uses the same tools
(with the delegation change noted below), the same system prompt plus a spoken-style addendum,
and the same session (`session_id` = `thread_id`), so text and voice turns share one history.

- **Model:** the voice model defined under "Model" below, driven through ADK's native Gemini
  live connection (`Runner.run_live`, `StreamingMode.BIDI`). ADK live mode is Gemini-only; a
  LiteLLM-wrapped model cannot hold a bidirectional connection, so the voice agent is built on
  ADK's native Gemini model rather than the LiteLlm adapter (ADK ≥ 2.9 recognizes 3.x live
  model names and streams microphone audio with the SDK's `audio` realtime input).
- **Session config:** response modality AUDIO; input and output audio transcription enabled;
  session resumption and sliding-window context compression enabled so a conversation is not
  cut by the Live API's per-connection limit. Audio blobs are not persisted to the ADK session;
  transcriptions are (as `user` / `model` events), which is what later text turns see.
- **Availability:** voice mode is available when the voice model's provider key
  (`GEMINI_API_KEY`) is set; otherwise the API shall refuse to open a voice session (`api.md`).
- **Turn handling:** the system shall stream the user's microphone audio into the live session
  and stream the model's audio back as it is produced. When the user speaks while the model is
  speaking (barge-in), the system shall stop forwarding the interrupted response and tell the
  client to discard buffered playback.
- **Transcript persistence:** when a voice turn completes, the system shall publish the turn on
  the internal event bus as an `InitMessage` (user transcription) and a `Result` (assistant
  transcription) flagged `voice=true`. The chat service persists them as `user` / `result`
  messages with `metadata.voice = true` (`state.md`) and titles the thread as for text turns,
  but shall not relay them as SSE events — the voice client receives transcripts over its own
  connection (`api.md`). Episodic memory consumes them like any other turn.
- **Tools in voice mode:** function tools execute inside the live loop, and a blocking tool
  silences the conversation. Therefore, in voice mode `delegate_to_task_agent` shall behave
  like `dispatch_background_task`: start the task agent in the background and return
  immediately. While a voice session is open on a thread, the system shall deliver that
  thread's finished background-task results into the live session as a user-role content
  message (instead of running a text turn of the front agent) so the model narrates the result
  aloud. If the voice session has ended by then, the result is delivered as a plain
  background-task `result` on the thread (SSE), as when no front agent is available.
  `browse` follows the same rule: in voice mode it creates a background task row
  (`state.md`, `tasks`) whose label starts with `Browse:`, runs the browser loop in the
  background, and delivers the result through the same path.
- **Cost:** audio streamed in each direction is accumulated per voice turn, priced by duration
  with the voice model's per-minute rates (see "Cost tracking"), and reported on the persisted
  `result` message.

### Task agent
- **Role:** the executor — runs shell commands, reads/writes files, fetches the web, drives
  skills, and uses MCP integrations. One instance per thread, session persisted across calls.
- **Behavior:** the system shall present a delegated task's result back through the front
  agent, lightly cleaned, in full. The front agent shall reuse an existing `task_id` for
  continued work on the same task rather than creating a new one.
- **Images:** the task agent is the only agent that can show the user an image. It shall do so
  through `send_image` (any browser-renderable image file on disk) or `render_diagram`
  (Mermaid source), never by replying with a filesystem path or telling the user to open a file.
  Both publish an `image` event on the owning chat thread (`api.md`), which persists the image
  as an `image` message (`state.md`) and streams it to the thread's SSE subscribers.

### Personas ("hats")
Six single-lens reasoning personas — white (facts), red (emotion), black (risks), yellow
(benefits), green (creativity), blue (process). Each is a lightweight tool-less agent the
front agent consults via `consult_persona`; consulted personas are recorded on the result.

## Model

A single model id is configured for both agents (currently `gemini/gemini-3.5-flash-lite`,
priced $0.30/M input, $2.50/M output). The conversation **titler** uses
`anthropic/claude-haiku-4-5`; the **progress analyzer** uses an OpenAI mini model.

The **voice model** (voice mode only) is `gemini-3.8-live`, priced by audio duration at the
Live API's per-minute rates: $0.005/min audio input, $0.018/min audio output. It is defined
alongside the other model specs in the same single place.

The **browser decision model** is TypeSafe's `jev-latest` (System One), priced
$0.042/M input tokens with free output. It is text-only, answers typed questions (yes/no,
choice, score) over a state object in one ~300 ms request, and never generates text. It is
defined alongside the other model specs in the same single place and requires
`TYPESAFE_API_KEY`.

Note the open question below: the runtime has Anthropic-specific code paths (extended
thinking, prompt caching) that only activate for Claude models, so the effective model
matters. Record the model in exactly this place; do not duplicate it elsewhere.

## Tool inventory (task agent)

Tools are assembled from these sources:

- **Builtins** (4): `run_bash` (shell, 600 s timeout, 30K-char output cap), `read_file`,
  `write_file`, `fetch_url` (HTTP(S), 30 s, 100K-char cap).

Web access escalates: `fetch_url` is the default; when a page is JavaScript-rendered,
login-gated, or bot-blocked (Cloudflare etc.), the agent uses the **browser tools** (see
"Browser agent" below), which drive the shared resident host Chrome. The `agent-browser` CLI
is no longer offered to the model: its shell-driven daemon could hang a `run_bash` call for
the full timeout, so prompts and skills shall not mention `abr`.
- **Memory** (3, mem0 + pgvector + Ollama embeddings): `search_memories`, `add_memory`,
  `delete_memory`. Backs the semantic store in `state.md`.
- **Episodic** (2, Postgres): `episodic_search(query, days)`, `episodic_show(conversation_id)`.
  Backs the `conversations` store in `state.md`.
- **Scheduler** (6, APScheduler over Postgres): `add_job`, `add_one_shot_job`, `list_jobs`,
  `delete_job`, `delete_all_jobs`, `trigger_job`. Recurring/one-shot jobs fire task triggers
  via the internal pub/sub.
- **Projects** (task-agent subset): `list_projects`, `update_project`, `delete_project`
  (the thread-level project tools live on the front agent).
- **Images** (2, per thread): `send_image(path, caption="")` (a local file or an http(s) image
  URL, which the system fetches with a browser user agent; formats are sent as-is) and
  `render_diagram(diagram, caption="")` (see "Task agent", Images).
- **Skill version tools** (7): `skill_version_status`, `skill_baseline`, `skill_set_canary`,
  `skill_promote`, `skill_rollback`, `skill_list_executions`, `skill_record_outcome`.
- **Admin** (1): `notify`.
- **Browser** (per thread, see "Browser agent"): `browser_open`, `browser_observe`,
  `browser_act`, `browser_eval`, `browser_wait`, `browser_tabs`, `browser_screenshot`,
  `browser_close`, and — while `TYPESAFE_API_KEY` is set — `browser_do` and `browser_check`.
- **Skills** (dynamic): a `SkillToolset` built from `SKILL.md` files under the repo
  `skills/` and `~/.claude/skills/`. Skills are reloaded on each task so edits take effect
  immediately; the skill-discovery list tool is intentionally dropped to avoid prompt bloat.
- **MCP servers** (from `mcp_servers.json`, all HTTP, tool names prefixed):
  - `google_*` — Google services (Gmail, Calendar, etc.)
  - `todoist_ai_*` — Todoist task management
  - `notion_*` — Notion workspace
  MCP toolsets are prewarmed on startup to surface connection errors early.

## Browser agent

The browser agent lets both agents operate the **shared resident host Chrome** — a real,
headed Chrome window on the deploy host with persistent logins — from inside the container.
It attaches over the Chrome DevTools Protocol (`BROWSER_CDP_HTTP`, falling back to
`ABR_CDP_HTTP`) using Playwright, never launching a browser of its own, and it runs
in-process: no shell command, no daemon, so a browser call cannot hang the `run_bash`
timeout. Downloads triggered in that Chrome land in the host download folder mounted at
`/mounts/downloads`.

- **Session model:** each thread owns at most one tab, opened lazily by the first browser
  tool call and reused by later calls; `browser_close` closes only that tab, never the
  browser. `browser_tabs` lists the browser's tabs and can adopt one as the thread's tab.
  When an action opens a new tab or popup, the system shall adopt that tab as the thread's
  current tab and report it in the action's outcome, so a flow that continues on a
  file-hosting page is followed without the caller noticing the tab change.
- **Downloads:** the system shall watch every tab it owns for downloads. When a navigation
  or an action starts a file download, the outcome shall say so rather than fail, and a Jev
  loop shall stop with `done` and the reason "a file download was started" as soon as one
  begins, even if it begins during a wait.
- **Observation:** `browser_observe` returns the page's url, title, a capped excerpt of its
  visible text, visible alert/dialog text, scroll position, and an indexed table of visible
  interactive elements (`#ref kind 'name' …`). Refs are assigned fresh on each observation
  and become stale after the page changes. `browser_eval` runs JavaScript and returns its
  JSON result for deterministic extraction (links, hrefs, counts).
- **Actions:** `browser_act(action, ref, value)` performs one deterministic action —
  `click`, `type` (fill), `select`, `press` (a key), `scroll_down`, `scroll_up`, `back` —
  and returns the fresh observation. `browser_wait` waits for text, a CSS selector, or a
  JavaScript condition with a bounded timeout.
- **Jev loop (`browser_do(goal, values, max_steps, allow_irreversible)` / front `browse`):**
  an observe → decide → act → verify loop in which the browser decision model chooses
  every step. Per step the system shall send one request carrying the goal, the value
  names available, the pruned observation and the last few actions, and ask in parallel:
  the next `action` (choice), the `target` element (choice over refs), which named `value`
  to enter (choice), and three yes/no judgments — `goal_met`, `stuck`, `irreversible`.
  - The observation is pruned in code before it is sent: modal/dialog elements first, then
    in-viewport elements, then the rest ranked by word overlap with the goal, capped at
    `BROWSER_MAX_CANDIDATES`; the text excerpt is capped so state stays well under the
    model's limit. The target questions list candidates by ref number only
    (`BROWSER_JEV_CRITERIA=refs`, the default); the element descriptions live once in the
    state. `names` or `full` restore descriptions in the criteria at higher token cost.
  - Jev cannot write text, so typed/selected text comes only from the caller's `values`
    map. If the chosen action needs a value and none fits, the loop stops with
    `needs_input`.
  - If `goal_met` ≥ 0.8 the loop stops with `done` without acting. If `irreversible` ≥ 0.5
    and `allow_irreversible` is false the loop stops with `needs_confirmation` before
    acting. If the action is `blocked` the loop stops with `blocked`, quoting the page's own
    dialog or alert text when there is one. If `stuck` ≥ 0.8, or three consecutive non-wait
    actions leave the observation identical, the loop stops with `stuck`. Budgets end the
    loop with `max_steps` or `timeout` (`BROWSER_TIMEOUT_S`, overridable per call). The
    action `done` stops with `done` only when `goal_met` ≥ 0.5; otherwise the next most
    likely action is taken.
  - `wait` is adaptive: consecutive waits grow from 2 s up to 10 s so a page that is
    loading, clearing a challenge, or preparing a file (for example decrypting before a
    download) is given time without burning steps, and a download that begins during the
    wait ends the loop immediately.
  - The result is structured: `status`, final `url` and `title`, a text `summary` of the
    page, the `steps` taken, Jev token usage and `cost_usd`. The caller (an LLM) decides
    what to do with `needs_input`, `needs_confirmation`, or `stuck`: retry with values or a
    narrower goal, or take over with the deterministic tools.
- **`browser_check(question)`:** one yes/no judgment by the browser decision model over the
  current page's visible text, returning the probability.
- **Availability:** the deterministic tools are registered whenever a CDP endpoint is
  configured; `browser_do`, `browser_check`, and the front `browse` are registered only
  while `TYPESAFE_API_KEY` is set. When Chrome is unreachable a tool returns an error
  string rather than raising.
- **Concurrency:** at most `BROWSER_MAX_CONCURRENT` Jev loops run at once across threads.
- **Cost:** Jev usage (input tokens × the model's rate) is recorded as delegated cost of the
  running agent turn (see "Cost tracking") and as a per-call cost metric.
- **Screenshots:** `browser_screenshot` saves a PNG and shows it to the user through the
  same path as `send_image` (`api.md` `image` event); in voice mode the screenshot is saved
  but not shown, so the task agent uses `send_image` when the user asked to see the page.

## Skill versioning & self-heal

Skills carry **stable** and **canary** versions. The system shall let the agent capture a
baseline before editing (`skill_baseline`), snapshot edits as a canary (`skill_set_canary`),
and promote (`skill_promote`) or roll back (`skill_rollback`). Run outcomes are recorded to
the `job_executions` ledger (see `state.md`) with the skill version tags used. Automatic
promotion/rollback applies to scheduled jobs, not interactive tasks.

## Runtime knobs

Environment variables (defaults in parentheses):
- `LLM_THINKING_BUDGET` (2048) — extended-thinking budget, **Anthropic only**; enabled via
  `thinking={type: enabled, budget_tokens}` with beta header
  `interleaved-thinking-2025-05-14`.
- `LLM_MAX_OUTPUT_TOKENS` (32000) — Anthropic only.
- `LLM_PROMPT_CACHING` (1) — Anthropic only; cache-control injected at the system message
  and last user message; cached input billed at 0.1×.
- `MAX_TURNS` (100) — tool-invocation cap per run.
- `MAX_TOOL_OUTPUT_CHARS` (50000) — tool outputs truncated past this length.
- `FRONT_MAX_CONCURRENT_TASKS` (3), `FRONT_RECENT_TASKS` (10), `FRONT_AGENT_ENABLED` (1).
- `LLM_TITLE_MODEL` (`anthropic/claude-haiku-4-5`).
- `BROWSER_CDP_HTTP` (falls back to `ABR_CDP_HTTP`, then `http://192.168.65.254:9222`),
  `JEV_MODEL` (`jev-latest`), `BROWSER_MAX_STEPS` (20), `BROWSER_TIMEOUT_S` (120),
  `BROWSER_MAX_CONCURRENT` (2), `BROWSER_MAX_CANDIDATES` (80) — see "Browser agent".

## Cost tracking

After each model call the system shall capture token usage (prompt, candidates, cached) and
compute cost as `uncached_in/1M·in_rate + cached_in/1M·in_rate·0.1 + out/1M·out_rate`,
recording it to telemetry spans and metrics. Delegated-task cost is accumulated and added to
the originating session's cost, so a front-agent turn's reported `cost_usd` includes the
work it delegated. Browser-agent Jev usage is recorded the same way, so a turn that
browsed reports that cost too.

Live-session events carry no usage metadata, so voice turns are priced by audio duration
instead: bytes streamed in each direction at the fixed PCM rates (`api.md`) are converted to
minutes and multiplied by the voice model's per-minute rates. Text tokens exchanged in a voice
session (system prompt, tool results) are not metered.

## Progress & titling

- **Progress:** a progress analyzer consumes tool-call events (every few events) and emits a
  short present-continuous `progress` SSE summary (uses an OpenAI mini model; needs
  `OPENAI_API_KEY`).
- **Titling:** after the first result, a titler generates a 3–6 word thread title (Claude
  Haiku) emitted as a `title` SSE event and stored on the thread.

## Internal event bus

Agent work is decoupled via an in-process async pub/sub. Task execution publishes events
(`init`, tool calls, `thought`, `result`/`result_delta`, `progress`, `project_selected`,
`image`) that the chat service relays to SSE (`api.md`), the episodic service consumes to
build `conversations`, and the progress analyzer summarizes. The scheduler publishes task
triggers onto the same bus. Voice turns publish `InitMessage` / `Result` flagged `voice=true`
(see Voice mode).

## Open questions

1. **Configured model vs. Anthropic code paths.** The model id is a Gemini one, but
   thinking/caching/output-token knobs only take effect for Claude. Confirm the intended
   production model and either align the config or document that the Anthropic paths are
   dormant by design.
2. **In-process shell access.** The task agent runs unsandboxed with `run_bash`. Confirm
   this is the intended trust model, or specify the isolation boundary.
3. **Self-heal scope.** Automatic skill promotion/rollback covers scheduled jobs only.
   Confirm interactive tasks are intentionally excluded.
