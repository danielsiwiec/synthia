import json
import re
from dataclasses import dataclass

import litellm
from loguru import logger

from synthia.agents.agent import FRONT_MODEL

_REPORT_CHARS = 6000
_TRAIL_CHARS = 80000
_OBJECT = re.compile(r"\{.*\}", re.S)

_PROMPT = """You audit one run of a scheduled job done by an AI agent. Decide whether the run actually did its job.

Judge from the execution trail, not from the agent's claims. The final report may be wrong or overly positive.

The run FAILED if any of these is true:
- tools the job depended on errored or were unavailable, so required work was not done
  (infrastructure failure: a browser, service, site, script or API was down or erroring);
- the agent stopped before doing work the instruction asked for (e.g. found new items but never downloaded them),
  skipped required steps, or reported results that the trail does not support (task failure).

If the run worked on several items (e.g. several magazines), check EVERY item one by one:
- what the tool output (e.g. a check script's JSON) says about it — its local copy, what was found online, its status;
- whether that status is itself plausible (an online item newer than the local copy reported as "current" is a wrong
  verdict the run should have caught, and leaves the job incomplete);
- what the run then did with it (downloaded and verified, correctly reported as impossible, or silently dropped).
An issue spanning several months (e.g. "September-October 2026") is dated by its first month, so a local copy dated
that month is the same issue. A season (e.g. "Summer 2026") is later than a copy from earlier in that year's spring.
Any item that should have been acted on but was not makes the run a task failure.

Use cause "infrastructure" only when every item that was not done is explained by infrastructure; if any item failed
for a task reason (including a wrong status the run should have caught), the cause is "task".

Judge against the instruction's goal, not against the procedure in any loaded skill text: taking a different route to
the same verified result is fine.

Judge outcomes, not every command: an incidental command that failed is not a failure when the run worked around it
or the outcome is shown another way (e.g. a missing `file` tool, but the downloaded file's size was confirmed).

The run SUCCEEDED if it did everything the instruction asked that was possible. Work that was impossible for an
external reason the agent correctly reported (an item not published yet, not covered by a subscription, nothing new
to do) is not a failure. A tool, browser, site or service that errored or was unreachable is different: that is an
infrastructure failure even when the agent reports it honestly. Access refused because the user's account or
subscription does not include an item is an external limit, not an infrastructure failure.

Instruction:
{task}

Final report:
{report}

Execution trail (🔧 tool calls with their results, 💬 agent text):
{trail}

Answer with only a JSON object. List EVERY item first (for a single-item job, one entry), comparing the local and
online issue dates yourself rather than trusting the status field, then give the verdict:
{{"items": [{{"item": "<name>", "local": "<newest local copy>", "online": "<newest found online>",
  "status_in_data": "<status the tool reported>", "status_plausible": true or false,
  "outcome": "<downloaded | up to date | correctly reported impossible | not done>"}}],
 "success": true or false, "cause": "none" | "infrastructure" | "task",
 "reason": "<one or two sentences naming the items that were not done>"}}"""


@dataclass(frozen=True)
class Verdict:
    success: bool
    infrastructure: bool
    reason: str


def parse_verdict(text: str) -> Verdict | None:
    match = _OBJECT.search(text or "")
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    success = data.get("success")
    if not isinstance(success, bool):
        return None
    reason = str(data.get("reason") or "").strip()
    infrastructure = not success and data.get("cause") == "infrastructure"
    return Verdict(success=success, infrastructure=infrastructure, reason=reason)


def _fit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n…[middle of the trail omitted]…\n{text[-half:]}"


async def judge_run(task: str, report: str, trail: str, model: str = FRONT_MODEL) -> Verdict | None:
    prompt = _PROMPT.format(task=task, report=report[-_REPORT_CHARS:], trail=_fit(trail, _TRAIL_CHARS))
    try:
        response = await litellm.acompletion(model=model, messages=[{"role": "user", "content": prompt}])
    except Exception as error:
        logger.warning(f"outcome judge failed: {error}")
        return None
    verdict = parse_verdict(response.choices[0].message.content or "")
    if verdict is None:
        logger.warning("outcome judge returned an unparseable verdict")
    return verdict
