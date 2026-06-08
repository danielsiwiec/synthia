import random
import time
from pathlib import Path

import pytest

from synthia.agents.agent import Agent
from synthia.agents.builtins import create_builtin_tools
from synthia.service.models import TaskImage
from tests.helpers import write_band_png

_COLORS = {"red": (230, 0, 0), "green": (0, 170, 0), "blue": (0, 70, 230), "yellow": (240, 220, 0)}


def _read_file_tool(cwd: Path):
    return next(t for t in create_builtin_tools(cwd) if getattr(t, "__name__", "") == "read_file")


async def test_read_file_cannot_deliver_image(tmp_path):
    image = write_band_png(tmp_path / "bands.png", _COLORS["red"], _COLORS["blue"])
    read_file = _read_file_tool(tmp_path)

    output = await read_file(str(image))

    assert "Error reading file" in output
    assert "red" not in output and "blue" not in output


@pytest.mark.eval
async def test_vision_understands_attached_image(tmp_path):
    top_name, bottom_name = random.sample(list(_COLORS), 2)
    image = write_band_png(tmp_path / "bands.png", _COLORS[top_name], _COLORS[bottom_name])

    agent = await Agent.create(cwd=tmp_path)
    start = time.perf_counter()
    result = await agent.run_for_result(
        objective="What color is the TOP half of this image? Answer with a single lowercase word.",
        thread_id=random.randint(300000, 399999),
        images=[TaskImage(path=str(image), content_type="image/png")],
    )
    elapsed = time.perf_counter() - start

    assert result is not None and result.success, result
    print(f"\n  vision: top={top_name} answer={result.result!r} duration={elapsed:.1f}s tools={result.tool_call_names}")

    assert top_name in result.result.lower(), f"expected {top_name}, got {result.result!r}"
    assert "read_file" not in result.tool_call_names
    assert elapsed < 60, f"vision response took {elapsed:.1f}s"
