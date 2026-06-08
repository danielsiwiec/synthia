from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VERSIONS_DIR = ".versions"
LEDGER_FILE = "versions.json"
PROMOTE_AFTER_SUCCESSES = 3


def _versions_root(skill_dir: Path) -> Path:
    return skill_dir / VERSIONS_DIR


def _ledger_path(skill_dir: Path) -> Path:
    return _versions_root(skill_dir) / LEDGER_FILE


def _skill_files(skill_dir: Path) -> list[Path]:
    files = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        if VERSIONS_DIR in path.relative_to(skill_dir).parts:
            continue
        files.append(path)
    return files


def _content_hash(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in _skill_files(skill_dir):
        digest.update(str(path.relative_to(skill_dir)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _empty_ledger() -> dict[str, Any]:
    return {"active": None, "stable": None, "canary": None, "versions": []}


def _load_ledger(skill_dir: Path) -> dict[str, Any]:
    path = _ledger_path(skill_dir)
    if not path.exists():
        return _empty_ledger()
    try:
        return json.loads(path.read_text())
    except Exception:
        return _empty_ledger()


def _save_ledger(skill_dir: Path, ledger: dict[str, Any]) -> None:
    root = _versions_root(skill_dir)
    root.mkdir(parents=True, exist_ok=True)
    _ledger_path(skill_dir).write_text(json.dumps(ledger, indent=2))


def _find_version(ledger: dict[str, Any], tag: str) -> dict[str, Any] | None:
    for version in ledger["versions"]:
        if version["tag"] == tag:
            return version
    return None


def _copy_snapshot(skill_dir: Path, tag: str) -> None:
    dest = _versions_root(skill_dir) / tag
    if dest.exists():
        shutil.rmtree(dest)
    for path in _skill_files(skill_dir):
        rel = path.relative_to(skill_dir)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def _restore_snapshot(skill_dir: Path, tag: str) -> list[str]:
    src = _versions_root(skill_dir) / tag
    if not src.is_dir():
        raise FileNotFoundError(f"snapshot '{tag}' not found")
    for path in _skill_files(skill_dir):
        path.unlink()
    restored = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        target = skill_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        restored.append(str(rel))
    return restored


def snapshot(skill_dir: Path, status: str = "canary", notes: str = "") -> str:
    if status not in ("stable", "canary"):
        raise ValueError("status must be 'stable' or 'canary'")
    skill_dir = Path(skill_dir)
    ledger = _load_ledger(skill_dir)
    tag = _content_hash(skill_dir)

    if _find_version(ledger, tag) is None:
        _copy_snapshot(skill_dir, tag)
        ledger["versions"].append(
            {
                "tag": tag,
                "created_at": _now(),
                "status": status,
                "parent": ledger.get("stable"),
                "notes": notes,
                "runs": 0,
                "successes": 0,
                "failures": 0,
            }
        )

    ledger["active"] = tag
    if status == "stable":
        ledger["stable"] = tag
        ledger["canary"] = None
    else:
        ledger["canary"] = tag

    _save_ledger(skill_dir, ledger)
    return tag


def ensure_baseline(skill_dir: Path, notes: str = "initial baseline") -> str:
    skill_dir = Path(skill_dir)
    ledger = _load_ledger(skill_dir)
    if ledger.get("stable"):
        return ledger["stable"]
    return snapshot(skill_dir, status="stable", notes=notes)


def promote(skill_dir: Path, tag: str | None = None) -> dict[str, Any]:
    skill_dir = Path(skill_dir)
    ledger = _load_ledger(skill_dir)
    target = tag or ledger.get("canary")
    if not target:
        raise ValueError("no canary version to promote")
    version = _find_version(ledger, target)
    if version is None:
        raise ValueError(f"version '{target}' not found")
    for other in ledger["versions"]:
        if other["status"] == "stable":
            other["status"] = "retired"
    version["status"] = "stable"
    ledger["stable"] = target
    ledger["active"] = target
    ledger["canary"] = None
    _save_ledger(skill_dir, ledger)
    return {"promoted": target, "stable": target}


def rollback(skill_dir: Path) -> dict[str, Any]:
    skill_dir = Path(skill_dir)
    ledger = _load_ledger(skill_dir)
    stable = ledger.get("stable")
    canary = ledger.get("canary")
    if not stable:
        raise ValueError("no stable version to roll back to")
    restored = _restore_snapshot(skill_dir, stable)
    if canary:
        version = _find_version(ledger, canary)
        if version is not None:
            version["status"] = "retired"
    ledger["active"] = stable
    ledger["canary"] = None
    _save_ledger(skill_dir, ledger)
    return {"rolled_back_to": stable, "retired_canary": canary, "restored_files": restored}


def record_outcome(skill_dir: Path, tag: str, success: bool) -> dict[str, Any]:
    skill_dir = Path(skill_dir)
    ledger = _load_ledger(skill_dir)
    version = _find_version(ledger, tag)
    if version is None:
        raise ValueError(f"version '{tag}' not found")
    version["runs"] += 1
    if success:
        version["successes"] += 1
    else:
        version["failures"] += 1
    _save_ledger(skill_dir, ledger)
    return version


def should_promote(version: dict[str, Any]) -> bool:
    return version["failures"] == 0 and version["successes"] >= PROMOTE_AFTER_SUCCESSES


def status(skill_dir: Path) -> dict[str, Any]:
    return _load_ledger(Path(skill_dir))


def list_versions(skill_dir: Path) -> list[dict[str, Any]]:
    return _load_ledger(Path(skill_dir))["versions"]
