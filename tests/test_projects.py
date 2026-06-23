import json
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from synthia.agents.projects.client import create_project_tools
from synthia.agents.projects.tools.select_project import create_select_project_tool
from synthia.migrations.runner import run_migrations
from synthia.routes.chat import _project_context, list_projects
from synthia.service.chat import ChatService
from synthia.service.models import ProjectSelected
from synthia.service.project_repository import ProjectRepository


@pytest.fixture
async def repo(pgvector_container: str):
    run_migrations(pgvector_container)
    pool = await asyncpg.create_pool(pgvector_container, min_size=1, max_size=2)
    await pool.execute("DELETE FROM projects")
    try:
        yield ProjectRepository(pool)
    finally:
        await pool.close()


def _tools(repo: ProjectRepository) -> dict:
    create, list_, update, delete = create_project_tools(repo)
    return {
        "create_project": create,
        "list_projects": list_,
        "update_project": update,
        "delete_project": delete,
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
    tools = _tools(repo)

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
    tools = _tools(repo)
    project = await repo.create(name="X")

    result = await tools["update_project"](str(project["id"]), status="archived")

    assert "Invalid status" in result


@pytest.mark.smoke
async def test_list_projects_endpoint_serializes_all_fields(repo: ProjectRepository) -> None:
    await repo.create(name="API project", document="# Notes", next_step="ship the mvp")
    request: Any = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(project_repository=repo)))

    body = await list_projects(request)

    assert len(body) == 1
    assert body[0]["name"] == "API project"
    assert body[0]["status"] == "active"
    assert body[0]["next_step"] == "ship the mvp"
    assert body[0]["document"] == "# Notes"
    assert isinstance(body[0]["id"], str)
    assert body[0]["created_at"] is not None


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
