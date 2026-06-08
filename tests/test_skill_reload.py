import os
from pathlib import Path

import pytest

from synthia.agents.skills import build_skill_toolset, reload_skills


def _write_skill(home: Path, name: str, body: str) -> None:
    d = home / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\ndescription: demo\n---\n{body}\n")


@pytest.mark.smoke
def test_reload_skills_reflects_disk_edits(tmp_path: Path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "work"
    _write_skill(home, "demo", "VERSION_ONE")

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        toolset = build_skill_toolset(cwd=work)
        assert toolset is not None
        assert "VERSION_ONE" in toolset._skills["demo"].instructions

        _write_skill(home, "demo", "VERSION_TWO")
        count = reload_skills(toolset, cwd=work)

        assert count >= 1
        assert "VERSION_TWO" in toolset._skills["demo"].instructions
        assert "VERSION_ONE" not in toolset._skills["demo"].instructions
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        else:
            os.environ.pop("HOME", None)


@pytest.mark.smoke
def test_reload_skills_skips_when_unchanged(tmp_path: Path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "work"
    _write_skill(home, "demo", "BODY")

    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        toolset = build_skill_toolset(cwd=work)
        assert toolset is not None
        reload_skills(toolset, cwd=work)

        sentinel = {"sentinel": object()}
        toolset._skills = sentinel
        count = reload_skills(toolset, cwd=work)

        assert count == 1
        assert toolset._skills is sentinel
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        else:
            os.environ.pop("HOME", None)
