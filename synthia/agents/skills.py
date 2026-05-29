from pathlib import Path

import yaml
from google.adk.skills.models import Frontmatter, Resources, Script, Skill
from google.adk.tools.skill_toolset import ListSkillsTool, SkillToolset
from loguru import logger


def _skill_dirs(cwd: str | Path | None) -> list[Path]:
    base = Path(cwd) if cwd else Path.cwd()
    return [base / ".claude" / "skills", Path.home() / ".claude" / "skills"]


def _load_dir(path: Path) -> dict[str, str | bytes]:
    out: dict[str, str | bytes] = {}
    if path.is_dir():
        for f in sorted(path.rglob("*")):
            if f.is_file():
                try:
                    out[str(f.relative_to(path))] = f.read_text()
                except Exception:
                    pass
    return out


def _load_skill(skill_dir: Path) -> Skill:
    md = skill_dir / "SKILL.md"
    if not md.exists():
        md = skill_dir / "skill.md"
    text = md.read_text()

    frontmatter_data: dict = {}
    body = text
    stripped = text.lstrip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) == 3:
            parsed = yaml.safe_load(parts[1])
            frontmatter_data = parsed if isinstance(parsed, dict) else {}
            body = parts[2].lstrip("\n")

    frontmatter_data["name"] = skill_dir.name
    if not frontmatter_data.get("description"):
        frontmatter_data["description"] = skill_dir.name

    return Skill(
        frontmatter=Frontmatter.model_validate(frontmatter_data),
        instructions=body,
        resources=Resources(
            references=_load_dir(skill_dir / "references"),
            assets=_load_dir(skill_dir / "assets"),
            scripts={
                n: Script(src=c if isinstance(c, str) else c.decode(errors="replace"))
                for n, c in _load_dir(skill_dir / "scripts").items()
            },
        ),
    )


def build_skill_toolset(cwd: str | Path | None = None) -> SkillToolset | None:
    skills = []
    for parent in _skill_dirs(cwd):
        if not parent.is_dir():
            continue
        for skill_dir in sorted(parent.iterdir()):
            if (
                not skill_dir.is_dir()
                or not (skill_dir / "SKILL.md").exists()
                and not (skill_dir / "skill.md").exists()
            ):
                continue
            try:
                skills.append(_load_skill(skill_dir))
                logger.info(f"Loaded skill: {skill_dir.name}")
            except Exception as error:
                logger.warning(f"Skipping skill '{skill_dir.name}': {error}")

    if not skills:
        return None

    toolset = SkillToolset(skills=skills)
    # Drop the list_skills tool so the full skill catalog (L1 metadata) is injected into the
    # system prompt every request. Without this the model must proactively call list_skills to
    # discover skills, which it does unreliably once many other tools are present.
    toolset._tools = [t for t in toolset._tools if not isinstance(t, ListSkillsTool)]
    return toolset
