from pathlib import Path

import pytest

from synthia.agents.skilltools import versions
from synthia.agents.skilltools.client import create_skilltools_tools


def _make_skill(root: Path, name: str, body: str = "v1") -> Path:
    skill_dir = root / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\ndescription: test\n---\n{body}\n")
    (skill_dir / "scripts" / "run.py").write_text("print('hello')\n")
    return skill_dir


@pytest.mark.smoke
def test_baseline_is_idempotent_and_snapshots_files(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, "magazines")

    tag = versions.ensure_baseline(skill_dir)
    again = versions.ensure_baseline(skill_dir)

    assert tag == again
    ledger = versions.status(skill_dir)
    assert ledger["stable"] == tag
    assert ledger["active"] == tag
    assert ledger["canary"] is None
    snapshot = skill_dir / versions.VERSIONS_DIR / tag / "SKILL.md"
    assert snapshot.exists()


@pytest.mark.smoke
def test_versions_dir_is_excluded_from_hash_and_snapshots(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, "arr")
    baseline = versions.ensure_baseline(skill_dir)
    # Re-hashing after a snapshot exists must not change the tag.
    assert versions._content_hash(skill_dir) == baseline


@pytest.mark.smoke
def test_canary_then_rollback_restores_stable_files(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, "magazines", body="v1")
    stable = versions.ensure_baseline(skill_dir)

    (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\nv2-optimized\n")
    canary = versions.snapshot(skill_dir, status="canary", notes="faster fetch")

    assert canary != stable
    ledger = versions.status(skill_dir)
    assert ledger["canary"] == canary
    assert ledger["active"] == canary
    assert ledger["stable"] == stable

    result = versions.rollback(skill_dir)
    assert result["rolled_back_to"] == stable
    assert "v1" in (skill_dir / "SKILL.md").read_text()
    ledger = versions.status(skill_dir)
    assert ledger["active"] == stable
    assert ledger["canary"] is None


@pytest.mark.smoke
def test_record_outcome_and_promotion_threshold(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, "magazines")
    versions.ensure_baseline(skill_dir)
    (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\nv2\n")
    canary = versions.snapshot(skill_dir, status="canary")

    for _ in range(versions.PROMOTE_AFTER_SUCCESSES - 1):
        versions.record_outcome(skill_dir, canary, success=True)
    version = next(v for v in versions.list_versions(skill_dir) if v["tag"] == canary)
    assert not versions.should_promote(version)

    version = versions.record_outcome(skill_dir, canary, success=True)
    assert versions.should_promote(version)

    versions.promote(skill_dir)
    ledger = versions.status(skill_dir)
    assert ledger["stable"] == canary
    assert ledger["canary"] is None


@pytest.mark.smoke
def test_a_failure_blocks_promotion(tmp_path: Path) -> None:
    skill_dir = _make_skill(tmp_path, "magazines")
    versions.ensure_baseline(skill_dir)
    (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\nv2\n")
    canary = versions.snapshot(skill_dir, status="canary")

    versions.record_outcome(skill_dir, canary, success=True)
    versions.record_outcome(skill_dir, canary, success=False)
    for _ in range(versions.PROMOTE_AFTER_SUCCESSES):
        versions.record_outcome(skill_dir, canary, success=True)

    version = next(v for v in versions.list_versions(skill_dir) if v["tag"] == canary)
    assert not versions.should_promote(version)


@pytest.mark.smoke
async def test_tools_refuse_unknown_or_builtin_skill(tmp_path: Path) -> None:
    _status, skill_baseline, *_rest = create_skilltools_tools(user_skills_dir=tmp_path)
    out = await skill_baseline("does-not-exist")
    assert "may only modify user skills" in out


@pytest.mark.smoke
async def test_set_canary_rejects_noop_edit(tmp_path: Path) -> None:
    _make_skill(tmp_path, "magazines")
    _status, skill_baseline, skill_set_canary, *_rest = create_skilltools_tools(user_skills_dir=tmp_path)
    await skill_baseline("magazines")
    out = await skill_set_canary("magazines", "no change made")
    assert "identical to the stable version" in out
