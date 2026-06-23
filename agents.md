## Running tests
uv run pytest ... -n auto --testmon

## Package management
- always add and remove packages using uv add/uv remove
- to update dependencies, use the `/update-dependencies` skill

## Verifying changes
- run `make check` after all changes
- after every change run the tests with the smoke marker. Do not use testmon or xdist for smoke test
- run all tests only after larger code changes
- when running multiple tests for verification, use xdist with `-n auto`

## Code style
- never add comments or docstrings
- use `_` prefix for all internal functions and fields that are not consumed outside of the module

## Tests
- when writing tests, do not use any mocks or patches, unless instructed to

## Inspecting synthia sessions (for analysis)
All chat and agent state lives in Postgres in the `pgvector` container, database `vector_store`.
Query it with: `docker exec pgvector psql -U postgres -d vector_store -c "<SQL>"`
(on the `mini` host the docker binary is `/usr/local/bin/docker`; prefix remote calls with
`ssh dansiwiec@mini`). Add `-t -A -F'|'` for clean, script-friendly output.

Data model:
- `threads` / `messages` — user-facing chat. `messages(thread_id, role, content, created_at)`;
  `thread_id` is a bigint.
- `tasks` — heavy task-agent runs the front agent delegated. `tasks(id, thread_id, status, background,
  label, request, result, created_at, updated_at)`; `id` is `task-<uuid>`, `status` is
  running/done/error, `background` is f (sync delegate) or t (background dispatch).
- `sessions` — ADK agent sessions. `id` equals the `thread_id` for chat sessions or the `task-<uuid>`
  for task sessions; `sessions(id, app_name, state, update_time)`.
- `events` — ADK per-turn events for a session. `events(session_id, timestamp, event_data)` where
  `event_data` is JSONB holding `content.parts[].{text,function_call,function_response}`,
  `usage_metadata`, `finish_reason`, and `error_message`.
- `thread_sessions` — maps `thread_id` <-> `session_id`.

Common recipes:
- Find a session/thread by something you remember being said:
  `select id, thread_id, role, left(content,80), created_at from messages where content ilike '%TEXT%' order by created_at desc;`
- List recent sessions (chat + task), most recent first:
  `select id, app_name, update_time from sessions order by update_time desc limit 20;`
- Read a chat transcript: `select role, left(regexp_replace(content,E'[\n\r]+',' ','g'),200), created_at from messages where thread_id=THREAD order by created_at;`
- List a thread's task-agent runs and status: `select id, status, background, label, created_at, updated_at from tasks where thread_id=THREAD order by created_at;`
- Trace what an agent did in a session (tool calls + text per turn):
  `select timestamp, jsonb_path_query_array(event_data::jsonb,'$.content.parts[*].function_call.name'), left(jsonb_path_query_array(event_data::jsonb,'$.content.parts[*].text')::text,160) from events where session_id='SESSION' order by timestamp;`
- Diagnose token/finish issues (truncation, context growth):
  `select timestamp, event_data::jsonb #>> '{usage_metadata,prompt_token_count}', event_data::jsonb #>> '{usage_metadata,candidates_token_count}', event_data::jsonb ->> 'finish_reason', event_data::jsonb ->> 'error_message' from events where session_id='SESSION' and event_data::jsonb ? 'usage_metadata' order by timestamp desc;`

## Additional resources
IMPORTANT: review extras/extra.md for additional instructions if it exists
