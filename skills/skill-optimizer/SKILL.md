---
description: Autonomously review past executions of recurring daily-job skills and optimize them to reduce failures, latency, and cost. Use when asked to optimize skills, improve a daily job, reduce job failures/cost, or run the skill optimizer. Also runs on a daily schedule.
---

## Overview

Reviews recent executions of **user-defined** skills (the ones that back recurring daily jobs, e.g. the
magazine check), diagnoses why a skill is failing / slow / expensive, changes the skill, validates it in
isolation, and ships the change as a monitored **canary** version. The daily-run self-heal guard
automatically rolls a canary back to the last stable version if it fails in production, and promotes it to
stable once it has enough successful runs — so a bad optimization can never break a job for more than one
run. Skill changes take effect on the next run with no restart (skills are reloaded from disk per run).

You may only modify **user skills** under `/home/synthia/.claude/skills/`. Built-in skills are read-only;
the version tools will refuse them.

### Two modes — and why exploration matters

1. **Minimal-fix mode** — a specific defect (a failing call, a retry loop, a wrong param). Make the small,
   obvious correction. Use this when the diagnosis is a localized bug.
2. **Exploration mode** — the skill *works* but is structurally inefficient (e.g. it walks N items one at a
   time through the agent loop, dozens of sequential tool calls). A minimal fix here only trims the edges
   and leaves you stuck in a **local optimum**. Instead, generate **2–3 genuinely different approaches** to
   the same goal, **measure** them, and ship the best. This is how the optimizer escapes local optima.

A run is structurally inefficient (→ exploration mode) when the dominant cost is **many repeated, similar
tool calls** — the clearest tell is a high `tool_call_count`. Cost is mostly cached-context reads that scale
with the number of agent turns, so **cutting turns is the highest-leverage lever**, and a redesign that
collapses N sequential operations into one batched/parallel operation moves the metric stepwise.

## Tools you will use

- `skill_list_executions(skill, days)` — recorded runs of a skill (success, cost, duration, tool-call count).
- `skill_version_status(skill)` — the version ledger (active / stable / canary tags + per-version outcomes).
- `skill_baseline(skill)` — snapshot current files as the stable baseline. **Call before editing.**
- `skill_set_canary(skill, notes)` — snapshot the edited files as a canary and make it active. **Call after editing + validating.**
- `skill_rollback(skill)` / `skill_promote(skill)` — abandon / promote a canary manually.
- `read_file`, `write_file`, `run_bash`, `run_skill_script`, `load_skill_resource` — read evidence, edit the skill, run validations.
- `episodic_search(query, days)` — pull transcripts of past runs.

## Steps

### 1. Pick a target skill and a mode

- Call `skill_list_executions` for the candidate user skills (or rely on recent failures you were told about).
- Rank by pain, worst first: (a) any failures, (b) high `tool_call_count` (the primary efficiency signal —
  it is robust to external network variance, unlike cost/duration), (c) high `cost_usd`, (d) high `duration_s`.
- Choose the single worst skill this run. If no skill has ≥3 recorded executions, there is not enough
  evidence — stop and report "insufficient data", do not guess.
- **Decide the mode:** if the pain is a discrete bug → minimal-fix mode (steps 3–6). If the pain is high
  `tool_call_count` from many repeated/sequential operations → **exploration mode** (see the Exploration
  section below) — a minimal fix will not escape the local optimum.

### 2. Gather evidence

- Read the failing/slow runs: `episodic_search("<skill name> <symptom>", days=14)` and inspect the
  transcripts. **Note:** stored tool outputs are truncated to ~500 chars — treat them as pointers, not
  ground truth, and reproduce the real step in step 4 when you need the full output.
- Read the current skill files: `read_file /home/synthia/.claude/skills/<skill>/SKILL.md` and any
  `scripts/`.
- Form a concrete diagnosis: a specific failing tool call, a redundant/duplicated step, an over-broad
  fetch, brittle parsing, a retry loop, an expensive model detour, etc. Write it down. If you cannot
  point to a specific waste, stop and report — do not make speculative edits.

### 3. Baseline, then edit

1. `skill_baseline("<skill>")` — capture the current known-good files as stable. **Never skip this.**
2. Make the **minimal** edit that addresses the diagnosis (edit `SKILL.md` and/or `scripts/` with
   `write_file`). Keep the change small and attributable to the diagnosis. Do not rewrite the skill.

### 4. Validate the CHANGED subcomponents only

Do **not** re-run the whole job. Validate just what you changed:

- **Changed scripts** (`scripts/*.py`, `scripts/*.sh`):
  - Syntax: `python -m py_compile <script>` for Python; `bash -n <script>` and, if available,
    `shellcheck <script>` for shell.
  - Behavior: run the script in isolation against a representative input you captured from a past
    transcript (use `run_skill_script` or `run_bash` with a dry-run / safe flag where the script
    supports one). Confirm it produces the expected output and exits 0.
- **Changed prompt steps** (instructions in `SKILL.md`):
  - Reproduce the concrete mechanical actions that step describes (the actual fetch / API call / parse)
    using a captured input, and check the result matches what the step is supposed to produce.
  - Compare against the baseline behaviour: it must be at least as correct, and ideally cheaper/fewer
    steps. If you cannot mechanically reproduce a step, treat it as **not validated**.

Record each subcomponent's verdict (pass / fail / not-validated).

### 5. Decide

- **All changed subcomponents pass** → `skill_set_canary("<skill>", notes="<what changed + why>")`. The
  canary is now live and monitored; the self-heal guard handles promotion/rollback over real runs.
- **Any subcomponent fails or could not be validated** → `skill_rollback("<skill>")` to restore stable
  (or simply re-write the original file), and leave the skill unchanged.

### 6. Report

- Write a short markdown report to `/home/synthia/.claude/data/skill-optimizations/<YYYY-MM-DD>-<skill>.md`
  with: target skill, diagnosis, the diff/summary of the edit, subcomponent verdicts, and the decision
  (canary tag or reverted).
- Send a one-line summary with the `notify` tool.

## Exploration mode (escaping local optima)

Use this when the bottleneck is structural (high `tool_call_count` from repeated/sequential work), not a
discrete bug. Here you are allowed — expected — to make **larger, structural changes** (new scripts, a
different control flow, a different tool/API), not just minimal edits. The safety rails are unchanged:
baseline first, validate, and only ship a **measured** winner.

1. **State the goal abstractly**, decoupled from the current implementation. E.g. *"determine, for each of
   the ~11 magazine titles, whether a newer issue exists online than the local copy"* — the goal is the
   verdict table, not "drive a browser to one search page at a time."

2. **Generate 2–3 genuinely different candidate approaches.** Make them architecturally distinct, e.g.:
   - **A — status quo + micro-fix** (the baseline, as a control).
   - **B — batch script**: one script that does all N items in a single invocation and returns a compact
     result table, so the agent makes ~1 call instead of ~N×k.
   - **C — parallel / headless**: do the N items concurrently (e.g. async HTTP, or one headless browser
     context per item in parallel) inside that script.
   Write each candidate as a real artifact in a scratch dir (e.g. `scripts/_cand_B.py`), not just prose.

3. **Measure each candidate** (see *Measuring improvement*). Record the metric per candidate.

4. **Pick the winner**: the candidate with the best measured primary metric (fewest projected agent turns
   / lowest wall-time) that also **passes correctness** (produces the same verdicts as the baseline on a
   known input). Discard the rest.

5. **Restructure the skill** to use the winner: move the per-item work into the chosen script and rewrite
   the relevant `SKILL.md` step so the agent invokes that one script instead of looping. Keep the download/
   side-effect steps intact unless they were part of the bottleneck.

6. Then proceed to validation + decide + report exactly as in the minimal-fix path, but the canary decision
   additionally **requires a measured improvement** over baseline above the noise threshold (below).

## Measuring improvement

Improvement must be **measured**, not asserted. Primary metric: **agent tool-call count (turns)** — it is
the most robust to external variance and directly reflects the architecture. Secondary: wall-time, then cost.

- **Subcomponent benchmark (do this inside your run):** run the candidate artifact standalone via
  `run_bash` against a fixed, representative input captured from a past transcript (e.g. the current local
  inventory + the title list). Record: wall-time (`time`), number of external calls it makes, and whether
  its output **matches the baseline verdicts** (correctness gate). A batch/parallel candidate should check
  all N items in seconds and replace ~N×k agent turns with ~1 — that projected turn reduction is your
  measured signal.
- **Noise threshold:** only ship if the projected primary-metric improvement is **large and clearly above
  noise** (rule of thumb: ≥30% fewer agent turns, or an order-of-magnitude subcomponent speedup). Small
  deltas are indistinguishable from run-to-run variance — do not ship those as "wins".
- **System-level confirmation (after shipping):** the canary's real runs are recorded in `job_executions`
  with `tool_call_count`. Compare the canary's runs to the pre-change baseline rows for the same job. State
  the before/after `tool_call_count` explicitly in your report. If the canary does **not** actually reduce
  turns over its first runs, treat it as a failed experiment and `skill_rollback`.
- Be honest about confounds: file downloads and external site latency dominate wall-time and vary run to
  run, so lead with the **turn-count** delta and treat cost/duration as secondary, noisy signals.

## Scheduling (self-registration)

Register the daily run once (idempotent — `add_job` replaces by name):

```
add_job(
  name="skill-optimizer-daily",
  start_date="<tomorrow at 04:00 in ISO format>",
  seconds=86400,
  task="Run the skill-optimizer skill: review recorded executions of user skills and optimize the single worst-performing one.",
  silent=false,
)
```

## Guardrails

- User skills only — never edit built-in skills.
- Always `skill_baseline` before the first edit so rollback is always possible.
- In **minimal-fix mode**, make one small change. In **exploration mode**, structural rewrites are allowed,
  but you must compare ≥2 candidates and ship only a **measured** winner.
- Never canary a change whose correctness you could not validate, or (in exploration) that does not show a
  measured improvement above the noise threshold.
- Lead with the **tool-call-count** metric; treat cost/duration as noisy secondary signals.
- Preserve correctness: the optimized skill must produce the same outcomes (same verdicts, same downloads)
  as the baseline on a known input.
- Insufficient evidence → stop and report, do not guess.

## Example Usage

- "Optimize the worst-performing daily job"
- "Run the skill optimizer"
- "Reduce failures in the magazine check skill"
- "Make my daily jobs cheaper and faster"
