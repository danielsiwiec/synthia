import json
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from synthia.agents.projects.client import create_project_thread_tools, create_project_tools
from synthia.agents.projects.tools.select_project import create_select_project_tool
from synthia.migrations.runner import run_migrations
from synthia.routes.chat import _project_context, list_projects
from synthia.service.chat import ChatService, MessageRepository
from synthia.service.models import ProjectSelected
from synthia.service.project_repository import ProjectRepository


@pytest.fixture
async def repo(pgvector_container: str):
    run_migrations(pgvector_container)
    pool = await asyncpg.create_pool(pgvector_container, min_size=1, max_size=2)
    await pool.execute("DELETE FROM threads")
    await pool.execute("DELETE FROM projects")
    try:
        yield ProjectRepository(pool)
    finally:
        await pool.close()


async def _tools(repo: ProjectRepository, thread_id: int = 1, tmp_path: Any = None) -> dict:
    list_, update, delete = create_project_tools(repo)
    chat = ChatService(repo._pool, cwd=tmp_path)
    await chat.initialize()
    await chat.repository.save_thread(thread_id, "thread")
    create, _select, add_section, attach_media = create_project_thread_tools(repo, chat, thread_id)
    return {
        "create_project": create,
        "list_projects": list_,
        "update_project": update,
        "delete_project": delete,
        "add_project_section": add_section,
        "attach_project_media": attach_media,
        "message_repository": chat.repository,
        "chat_service": chat,
    }


@pytest.mark.smoke
async def test_create_defaults_to_active_with_timestamps(repo: ProjectRepository) -> None:
    project = await repo.create(name="Kitchen remodel", document="# Plan\n- demo cabinets")

    assert project["name"] == "Kitchen remodel"
    assert project["status"] == "active"
    assert project["document"] == "# Plan\n- demo cabinets"
    assert project["created_at"] is not None
    assert project["updated_at"] is not None


@pytest.mark.smoke
async def test_update_changes_only_given_fields(repo: ProjectRepository) -> None:
    project = await repo.create(name="Trip", document="original", next_step="book flights")

    updated = await repo.update(project_id=str(project["id"]), status="closed")

    assert updated is not None
    assert updated["status"] == "closed"
    assert updated["name"] == "Trip"
    assert updated["document"] == "original"
    assert updated["next_step"] == "book flights"


@pytest.mark.smoke
async def test_update_next_step(repo: ProjectRepository) -> None:
    project = await repo.create(name="Trip", next_step="book flights")

    updated = await repo.update(project_id=str(project["id"]), next_step="reserve hotel")

    assert updated is not None
    assert updated["next_step"] == "reserve hotel"
    assert updated["name"] == "Trip"


@pytest.mark.smoke
async def test_list_orders_newest_first(repo: ProjectRepository) -> None:
    first = await repo.create(name="First")
    second = await repo.create(name="Second")

    projects = await repo.list_all()

    assert [p["name"] for p in projects] == ["Second", "First"]
    assert {str(first["id"]), str(second["id"])} == {str(p["id"]) for p in projects}


@pytest.mark.smoke
async def test_delete_removes_project(repo: ProjectRepository) -> None:
    project = await repo.create(name="Throwaway")

    assert await repo.delete(str(project["id"])) is True
    assert await repo.get(str(project["id"])) is None
    assert await repo.delete(str(project["id"])) is False


@pytest.mark.smoke
async def test_tools_round_trip(repo: ProjectRepository) -> None:
    tools = await _tools(repo)

    created = await tools["create_project"]("Garden", document="plant tomatoes")
    project_id = json.loads(created.split("\n", 1)[1])["id"]

    listing = json.loads(await tools["list_projects"]())
    assert listing[0]["name"] == "Garden"

    await tools["update_project"](project_id, status="closed", document="harvested")
    after = json.loads(await tools["list_projects"]())
    assert after[0]["status"] == "closed"
    assert after[0]["document"] == "harvested"

    assert "deleted" in await tools["delete_project"](project_id)
    assert "No projects found." in await tools["list_projects"]()


@pytest.mark.smoke
async def test_update_tool_rejects_invalid_status(repo: ProjectRepository) -> None:
    tools = await _tools(repo)
    project = await repo.create(name="X")

    result = await tools["update_project"](str(project["id"]), status="archived")

    assert "Invalid status" in result


@pytest.mark.smoke
async def test_list_projects_endpoint_serializes_all_fields(repo: ProjectRepository) -> None:
    await repo.create(name="API project", document="# Notes", next_step="ship the mvp")
    chat = ChatService(repo._pool)
    await chat.initialize()
    request: Any = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(project_repository=repo, chat_service=chat))
    )

    body = await list_projects(request)

    assert len(body) == 1
    assert body[0]["name"] == "API project"
    assert body[0]["status"] == "active"
    assert body[0]["next_step"] == "ship the mvp"
    assert body[0]["document"] == "# Notes"
    assert body[0]["thread_id"] is None
    assert body[0]["sections"] == []
    assert body[0]["media"] == []
    assert isinstance(body[0]["id"], str)
    assert body[0]["created_at"] is not None


@pytest.mark.smoke
async def test_add_section_appends_in_order(repo: ProjectRepository) -> None:
    tools = await _tools(repo)
    project = await repo.create(name="Garden")

    await tools["add_project_section"](str(project["id"]), title="Plan", body="dig")
    after = await tools["add_project_section"](str(project["id"]), title="Budget", body="$50")

    sections = json.loads(after.split("\n", 1)[1])["sections"]
    assert [s["title"] for s in sections] == ["Plan", "Budget"]
    stored = await repo.get(str(project["id"]))
    assert stored is not None
    assert [s["order"] for s in stored["sections"]] == [0, 1]


@pytest.mark.smoke
async def test_reorder_sections(repo: ProjectRepository) -> None:
    project = await repo.create(name="Trip")
    await repo.add_section(str(project["id"]), "A", "a")
    await repo.add_section(str(project["id"]), "B", "b")
    loaded = await repo.get(str(project["id"]))
    assert loaded is not None
    ids = [s["id"] for s in loaded["sections"]]

    reordered = await repo.reorder_sections(str(project["id"]), [ids[1], ids[0]])

    assert reordered is not None
    assert [s["title"] for s in reordered["sections"]] == ["B", "A"]


@pytest.mark.smoke
async def test_reorder_sections_rejects_mismatched_ids(repo: ProjectRepository) -> None:
    project = await repo.create(name="Trip")
    await repo.add_section(str(project["id"]), "A", "a")

    assert await repo.reorder_sections(str(project["id"]), ["nonexistent"]) is None


@pytest.mark.smoke
async def test_concurrent_add_media_keeps_all(repo: ProjectRepository) -> None:
    import asyncio

    project = await repo.create(name="Album")
    pid = str(project["id"])

    await asyncio.gather(
        *(
            repo.add_media(pid, name=f"f{i}.png", content_type="image/png", file=f"f{i}.png", caption="")
            for i in range(5)
        )
    )

    stored = await repo.get(pid)
    assert stored is not None
    assert sorted(m["name"] for m in stored["media"]) == [f"f{i}.png" for i in range(5)]
    assert sorted(m["order"] for m in stored["media"]) == [0, 1, 2, 3, 4]


@pytest.mark.smoke
async def test_concurrent_add_section_keeps_all(repo: ProjectRepository) -> None:
    import asyncio

    project = await repo.create(name="Plan")
    pid = str(project["id"])

    await asyncio.gather(*(repo.add_section(pid, f"S{i}", f"body{i}") for i in range(5)))

    stored = await repo.get(pid)
    assert stored is not None
    assert sorted(s["title"] for s in stored["sections"]) == [f"S{i}" for i in range(5)]


@pytest.mark.smoke
async def test_attach_media_stores_file_and_records_metadata(repo: ProjectRepository, tmp_path) -> None:
    tools = await _tools(repo, thread_id=7, tmp_path=tmp_path)
    project = await repo.create(name="Album")
    src = tmp_path / "shot.png"
    src.write_bytes(b"\x89PNG\r\n")

    result = await tools["attach_project_media"](str(project["id"]), str(src), caption="A shot")

    media = json.loads(result.split("\n", 1)[1])["media"]
    assert media[0]["name"] == "shot.png"
    stored = await repo.get(str(project["id"]))
    assert stored is not None
    assert stored["media"][0]["caption"] == "A shot"
    assert stored["media"][0]["content_type"] == "image/png"
    assert (tmp_path / "uploads" / "7" / "shot.png").exists()


@pytest.mark.smoke
async def test_attach_media_missing_file(repo: ProjectRepository, tmp_path) -> None:
    tools = await _tools(repo, thread_id=8, tmp_path=tmp_path)
    project = await repo.create(name="Album")

    result = await tools["attach_project_media"](str(project["id"]), str(tmp_path / "nope.png"))

    assert "not found" in result.lower()


@pytest.mark.smoke
async def test_create_project_binds_current_thread(repo: ProjectRepository) -> None:
    tools = await _tools(repo, thread_id=42)
    message_repo: MessageRepository = tools["message_repository"]

    created = await tools["create_project"]("Bound", document="x")
    project_id = json.loads(created.split("\n", 1)[1])["id"]

    assert await message_repo.thread_id_for_project(project_id) == 42
    threads = await message_repo.list_threads()
    assert all(t["id"] != 42 for t in threads)


@pytest.mark.smoke
async def test_project_context_includes_details(repo: ProjectRepository) -> None:
    project = await repo.create(name="Roof repair", document="# Roof\nfix the leak", next_step="call the roofer")
    request: Any = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(project_repository=repo)))

    ctx = await _project_context(request, str(project["id"]))

    assert "Roof repair" in ctx
    assert "fix the leak" in ctx
    assert "call the roofer" in ctx
    assert str(project["id"]) in ctx
    assert "status: active" in ctx


@pytest.mark.smoke
async def test_project_context_empty_for_missing_or_unset(repo: ProjectRepository) -> None:
    request: Any = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(project_repository=repo)))

    assert await _project_context(request, None) == ""
    assert await _project_context(request, "00000000-0000-0000-0000-000000000000") == ""
    assert await _project_context(request, "not-a-valid-uuid") == ""


@pytest.mark.smoke
async def test_select_project_tool_success_and_missing(repo: ProjectRepository) -> None:
    project = await repo.create(name="Garage", document="x")
    select_project = create_select_project_tool(repo, thread_id=123)

    ok = await select_project(str(project["id"]))
    missing = await select_project("00000000-0000-0000-0000-000000000000")

    assert "Garage" in ok
    assert "not found" in missing.lower()


@pytest.mark.smoke
async def test_handle_project_selected_pushes_sse_event(repo: ProjectRepository) -> None:
    chat = ChatService(repo._pool)
    await chat.initialize()
    await chat.repository.save_thread(555, "thread")
    queue = chat.event_bus.subscribe(555)

    await chat.handle_project_selected(ProjectSelected(thread_id=555, project_id="abc", name="Garage"))

    event = queue.get_nowait()
    assert event["type"] == "project_selected"
    assert event["project_id"] == "abc"
    assert event["name"] == "Garage"


@pytest.mark.smoke
async def test_handle_project_selected_ignores_unknown_thread(repo: ProjectRepository) -> None:
    chat = ChatService(repo._pool)
    await chat.initialize()
    queue = chat.event_bus.subscribe(999)

    await chat.handle_project_selected(ProjectSelected(thread_id=999, project_id="abc", name="X"))

    assert queue.empty()
