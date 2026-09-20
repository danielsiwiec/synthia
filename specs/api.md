# API Surface

Synthia is a FastAPI app (Uvicorn, port 8003) exposing a chat-based assistant over REST +
Server-Sent Events, plus Web Push. There is **no authentication**: every endpoint is
public and the system assumes a single user behind network isolation. CORS is not
configured (FastAPI default = same-origin). Data-model names below (thread, message, task,
project, etc.) are defined in `state.md`.

## HTTP routes

### Health
- **GET `/health`** → `{ "status": "healthy" }`.

### Chat UI & static
- **GET `/chat`** → serves the chat SPA (`static/app/index.html`, `Cache-Control: no-cache`).
- **GET `/static/{path}`** → static assets (app bundle, `manifest.json`, icons).
- **GET `/sw.js`** → the push service worker, with `Service-Worker-Allowed: /`.

### Threads
- **GET `/chat/threads`** → list of `{ id, title, created_at, updated_at }` (ids as strings).
- **PATCH `/chat/threads/{thread_id}`** — body `{ title }` (≤100 chars). If the title is
  empty after trimming, the system shall respond 400. Otherwise → `{ ok: true }`.
- **DELETE `/chat/threads/{thread_id}`** → `{ ok: true }`.
- **GET `/chat/threads/{thread_id}/messages`** → list of messages. Each item carries
  `id, thread_id, role, message_type, content, metadata, created_at` and, when present, a
  derived `attachments` array of `{ id, type, name, content_type, url }` where `url` points
  at the attachment endpoint below.
  Turns spoken in voice mode carry `metadata.voice = true`.
- **GET `/chat/threads/{thread_id}/attachments/{filename}`** → the raw attachment file with
  its content type. If the file is missing or the path escapes the thread's upload dir, the
  system shall respond 404.
- **POST `/chat/threads/{thread_id}/messages`** — send a user turn. Body:
  `{ content, reaction?, attachments?: [{name, content_type, data(base64)}], project_id?,
  persona? }`. Behavior:
  - If the thread does not exist, the system shall create it, titling it from the content
    or first attachment name.
  - If `project_id` is given and the thread is not yet linked, the system shall link them.
  - The system shall persist attachments to `uploads/{thread_id}/` and save the user
    message with its metadata. If `project_id` and attachments are both present, the
    attachments are also added to the project's media.
  - The system shall build the task prompt (user content + image metadata + file paths +
    project context + persona directive) and publish a task request internally.
  - → `{ ok: true }`. Image attachments are limited to the vision MIME types
    (`image/png, image/jpeg, image/gif, image/webp, image/heic, image/heif`); other files
    are passed to the agent as file paths.
- **POST `/chat/threads/{thread_id}/stop`** → publishes a stop request → `{ ok: true }`.

### Voice (WebSocket)
- **WS `/chat/threads/{thread_id}/voice`** — opens a live voice session on the thread (see
  `agent.md`, Voice mode). If voice mode is unavailable (voice model provider key not set), the
  system shall close the socket with code 1008 before any audio is exchanged. If the thread
  does not exist, the system shall create it, titled "Voice chat" until the titler runs. Only
  one voice session per thread is open at a time; opening a new one closes the previous.

  Client → server:
  - Binary frames: raw 16-bit little-endian PCM, mono, 16 kHz microphone audio.
  - Text frames (JSON): `{ "type": "end" }` ends the session cleanly.

  Server → client:
  - Binary frames: raw 16-bit little-endian PCM, mono, 24 kHz model audio, in playback order.
  - Text frames (JSON):

  | `type` | Payload | Meaning |
  | --- | --- | --- |
  | `ready` | — | Live session established; the client may start sending audio. |
  | `transcript` | `{ role: "user" \| "assistant", text, final }` | Cumulative transcription of the current speaker's turn; `final` marks the end of that turn. |
  | `interrupted` | — | The model's response was cut off by the user; discard buffered audio. |
  | `turn_complete` | `{ spoke }` | The model finished a turn; `spoke` is false for a turn that only issued tool calls (the spoken answer follows in a new turn). |
  | `error` | `{ message }` | The live session failed; the socket closes after this. |

  The system shall close the socket when the live session ends for any reason.

### Projects
- **GET `/chat/projects`** → list of projects with `id, name, status, next_step, document,
  thread_id, sections[], media[], created_at, updated_at`. Sections and media are sorted by
  their `order` field; media `url` resolves through the thread attachment endpoint (or null).
- **PATCH `/chat/projects/{project_id}/sections/reorder`** — body `{ section_ids: [...] }`
  in desired order. Invalid project or section ids → 400; otherwise `{ ok: true }`.

### Web Push
- **GET `/push/vapid-key`** → `{ public_key }` (base64url VAPID public key).
- **POST `/push/subscribe`** — body `{ endpoint, keys: { p256dh, auth } }`; upserts a
  `push_subscriptions` row → `{ ok: true }`.

VAPID flow: the client registers `/sw.js`, fetches the VAPID key, calls
`pushManager.subscribe()`, and posts the subscription. The server signs notifications with
`pywebpush` (claim `sub: mailto:noreply@synthia.dev`). On a 403/404/410 send failure the
system shall delete the stale subscription (see `state.md`). The service worker shows a
notification from `{ title?, body }` and, on click, focuses an existing `/chat` window or
opens one.

### Task (direct / internal)
- **POST `/task`** — body `{ task, thread_id, images?: [{path, content_type}], persona? }`.
  Runs the agent to completion and returns `{ thread_id, result, session_id }`. If the task
  is cancelled before completion the system shall respond 499. Primarily for internal /
  third-party callers, not the SPA.
- **POST `/stop?thread_id=...`** — cancels a running task (query param). Functionally
  overlaps with `/chat/threads/{thread_id}/stop` (see Open questions).

## SSE event stream

**GET `/chat/threads/{thread_id}/events`** opens a `text/event-stream` that stays open
until the client disconnects, with a `: keepalive` comment every 30 s. The frontend
(`@assistant-ui/react` + a Synthia runtime adapter) consumes it to render live turns.

Event types and payloads:

| Event | Payload | Meaning |
| --- | --- | --- |
| `connected` | — | Subscription registered; later events are guaranteed delivered. |
| `init` | `{ session_id, prompt }` | A task has begun; `prompt` is the full prompt sent to the model. |
| `thought` | `{ thinking }` | Intermediate model reasoning. Persisted as a `thought` message on chat threads. |
| `result_delta` | `{ delta }` | Incremental chunk of the result text (streaming). |
| `result` | `{ success, result, error?, cost_usd, persona?, consulted_personas? }` | Final result. Persisted as a `result` message on chat threads. |
| `progress` | `{ summary }` | Human-readable progress during long runs (see `agent.md`). |
| `title` | `{ title }` | Auto-generated thread title after the first result. |
| `image` | `{ caption, attachment: { type, name, content_type, url } }` | Agent-generated image (including browser screenshots), saved to uploads and persisted. |
| `project_selected` | `{ project_id, name }` | Agent opened/switched the active project. |

The system shall deliver SSE events whether or not the turn is persisted; persistence of
`thought`/`result` happens only for chat threads.

## Frontend↔backend contract

- **REST** for thread/project CRUD, sending messages (with base64 attachments), and stop.
- **SSE** per thread for live `init / thought / result_delta / result / progress / title /
  image / project_selected`.
- **WebSocket** per thread for voice mode: binary PCM audio in both directions plus JSON
  control/transcript frames (see Voice above). Voice transcripts reach the voice client only
  over this socket, never as SSE events.
- **Web Push** for out-of-band notifications (`{ title?, body }`).
- The frontend maps stored messages and SSE events onto assistant-ui content parts and
  infers a "running" state from the message sequence.

## Open questions

1. **Two stop endpoints.** `/stop` (query param, `task.py`) and
   `/chat/threads/{id}/stop` (path param) coexist; the SPA uses the latter. Decide whether
   to keep both, and document a single canonical stop contract.
2. **No auth / CORS.** Confirm the single-user, network-isolated assumption is the intended
   security model, or specify what should change before any multi-user/exposed deployment.
3. **Persona pass-through.** Persona is accepted on send and surfaced on results but has
   little backend behavior; clarify intended semantics so it isn't half-specified.
