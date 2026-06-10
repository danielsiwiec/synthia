import base64
from pathlib import Path

from synthia.agents.agent import _build_parts, create_image_tool
from synthia.service.chat import (
    _attachment_path,
    _safe_filename,
    _save_attachments,
    _save_image_file,
    _unique_path,
)
from synthia.service.models import TaskImage


def test_safe_filename_strips_paths():
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("a\\b\\c.png") == "c.png"
    assert _safe_filename("") == "attachment"


def test_unique_path_avoids_overwrite(tmp_path):
    existing = tmp_path / "f.txt"
    existing.write_text("x")
    assert _unique_path(existing) == tmp_path / "f_1.txt"


async def test_save_attachments_writes_files(tmp_path):
    data = base64.b64encode(b"hello").decode()
    saved = await _save_attachments(tmp_path, 7, [{"name": "note.txt", "content_type": "text/plain", "data": data}])

    assert len(saved) == 1
    path = Path(saved[0]["path"])
    assert path.read_bytes() == b"hello"
    assert path.parent == tmp_path / "7"
    assert saved[0]["name"] == "note.txt"
    assert saved[0]["content_type"] == "text/plain"


async def test_save_attachments_empty_returns_empty(tmp_path):
    assert await _save_attachments(tmp_path, 1, []) == []


async def test_save_attachments_sanitizes_traversal(tmp_path):
    data = base64.b64encode(b"x").decode()
    saved = await _save_attachments(tmp_path, 1, [{"name": "../escape.txt", "content_type": "", "data": data}])

    path = Path(saved[0]["path"])
    assert path.name == "escape.txt"
    assert path.parent == tmp_path / "1"


def test_attachment_path_resolves_within_thread_dir(tmp_path):
    path = _attachment_path(tmp_path, 5, "pixel.png")
    assert path == (tmp_path / "5" / "pixel.png").resolve()


def test_attachment_path_blocks_traversal(tmp_path):
    path = _attachment_path(tmp_path, 5, "../../secret.txt")
    assert path is not None
    assert path == (tmp_path / "5" / "secret.txt").resolve()
    assert path.parent == (tmp_path / "5").resolve()


async def test_save_image_file_copies_source(tmp_path):
    src = tmp_path / "shot.png"
    src.write_bytes(b"\x89PNG\r\n")
    dest = await _save_image_file(tmp_path, 9, src, "shot.png")
    assert dest.read_bytes() == b"\x89PNG\r\n"
    assert dest.parent == tmp_path / "9"


async def test_send_image_tool_rejects_missing_file(tmp_path):
    tool = create_image_tool(1, tmp_path)
    assert "no file found" in await tool("nope.png")


async def test_send_image_tool_rejects_non_image(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    tool = create_image_tool(1, tmp_path)
    assert "not an image" in await tool("a.txt")


async def test_send_image_tool_accepts_image(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG")
    tool = create_image_tool(1, tmp_path)
    assert "Sent image 'a.png'" in await tool("a.png")


def test_build_parts_includes_heic_image(tmp_path):
    image = tmp_path / "photo.heic"
    image.write_bytes(b"\x00\x00\x00\x18ftypheic")
    parts = _build_parts("hi", [TaskImage(path=str(image), content_type="image/heic")])
    assert len(parts) == 2
