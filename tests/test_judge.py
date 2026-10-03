import os
from pathlib import Path

import pytest

from synthia.agents.agent import FRONT_MODEL, required_api_key
from synthia.agents.judge import Verdict, judge_run, parse_verdict

_RUNS = Path(__file__).parent / "fixtures" / "judge"
_KEY = required_api_key(FRONT_MODEL)
_DAILY = (
    "Check for new issues of all subscribed magazines, including The Economist and Mountain Bike Action, "
    "and download them to Kavita."
)
_ECONOMIST = (
    "Use the magazines skill to check for a new issue of The Economist USA only (not any other titles). If a newer "
    "issue than the newest available/present is available, download it to Kavita following the full Mode 2 cycle."
)
_MBA = (
    "Use the magazines skill to check for a new issue of Mountain Bike Action USA only (not the other titles). If a "
    "newer issue is available, download it to Kavita following the full Mode 2 cycle."
)


@pytest.mark.smoke
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"success": true, "cause": "none", "reason": "ok"}', Verdict(True, False, "ok")),
        (
            'Verdict:\n{"success": false, "cause": "infrastructure", "reason": "browser down"}',
            Verdict(False, True, "browser down"),
        ),
        (
            '{"success": false, "cause": "task", "reason": "never downloaded"}',
            Verdict(False, False, "never downloaded"),
        ),
        ('{"success": true, "cause": "infrastructure", "reason": "x"}', Verdict(True, False, "x")),
        ('{"success": "yes"}', None),
        ("no json here", None),
        ("{not json}", None),
    ],
)
def test_parse_verdict(text: str, expected: Verdict | None) -> None:
    assert parse_verdict(text) == expected


@pytest.mark.eval
@pytest.mark.skipif(not (_KEY and os.getenv(_KEY)), reason=f"outcome judge needs {_KEY}")
@pytest.mark.parametrize(
    ("run", "task", "success", "infrastructure"),
    [
        ("infra_dead_browser", _DAILY, False, False),
        ("infra_unreachable_page", "Open http://127.0.0.1:1/ in the browser and report the page heading.", False, True),
        ("stopped_after_summary", _DAILY, False, False),
        ("daily_missed_season_issue", _DAILY, False, False),
        ("economist_downloaded", _ECONOMIST, True, False),
        ("mba_fallback_downloaded", _MBA, True, False),
    ],
)
async def test_judge_classifies_real_runs(run: str, task: str, success: bool, infrastructure: bool) -> None:
    report = (_RUNS / f"{run}.report.txt").read_text()
    trail = (_RUNS / f"{run}.trail.txt").read_text()
    verdict = await judge_run(task, report, trail)
    assert verdict is not None
    assert (verdict.success, verdict.infrastructure) == (success, infrastructure), verdict.reason
