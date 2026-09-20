# Synthia Specification — Table of Contents

This directory is the single, reconciled specification of Synthia's behavior and
functionality. It is organized by **concern**, not by feature: one fact lives in exactly
one file, and every other file references it by name. When you change Synthia, change the
relevant spec here first (see `.claude/skills/synthia-dev`), reconcile it against the
whole, then implement.

| File | What it covers |
| --- | --- |
| [state.md](state.md) | All persisted state and the canonical data model: every Postgres table, the two vector stores (episodic + semantic), filesystem storage, and ADK-managed session/event state. This file owns the system's vocabulary; other files reference its names. |
| [api.md](api.md) | The external HTTP/SSE/WebSocket surface: every route (chat, voice, projects, push, task, health), the SSE event stream and its event types, the voice WebSocket protocol, the Web Push/VAPID flow, and the frontend↔backend transport contract. |
| [agent.md](agent.md) | The agent architecture: the Google ADK framework, the front-agent / task-agent split, voice mode (live front agent), which model runs where, the full tool inventory by source, MCP servers, where/how agents execute, and runtime knobs (caching, thinking, cost, concurrency). |

## Conventions

- Testable behaviors use EARS phrasing where it fits ("When … the system shall …",
  "While …", "If … then …"). Structure and data models are described as prose.
- Each file ends with an **Open questions** section recording known ambiguities or
  apparent intended-vs-actual mismatches found while extracting the spec from code.
- Cross-cutting *repo workflow* rules (testing, packaging, code style, deploy) live in the
  repo's `CLAUDE.md` and `extras/extra.md`, not here. This spec describes Synthia's
  behavior; those describe how to work on the repo.
