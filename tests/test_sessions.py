import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from synthia.agents.sessions.client import SessionsClient


@pytest.fixture
def temp_projects_dir():
    with TemporaryDirectory() as tmpdir:
        projects_path = Path(tmpdir)
        project_dir = projects_path / "-home-test"
        project_dir.mkdir()
        yield projects_path


@pytest.fixture
def sessions_client(temp_projects_dir: Path) -> SessionsClient:
    return SessionsClient(temp_projects_dir)


def _create_session_file(project_dir: Path, session_id: str, messages: list[dict]) -> Path:
    session_file = project_dir / f"{session_id}.jsonl"
    with session_file.open("w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")
    return session_file


def test_list_sessions_empty(sessions_client: SessionsClient) -> None:
    result = sessions_client.list_sessions(10)
    assert result == []


def test_list_sessions_returns_sessions(temp_projects_dir: Path, sessions_client: SessionsClient) -> None:
    project_dir = temp_projects_dir / "-home-test"
    messages = [
        {
            "type": "user",
            "message": {"role": "user", "content": "hello world"},
            "timestamp": "2025-12-04T06:39:49.447Z",
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there! How can I help?"}],
            },
            "timestamp": "2025-12-04T06:39:52.447Z",
        },
    ]
    _create_session_file(project_dir, "test-session-123", messages)

    result = sessions_client.list_sessions(10)

    assert len(result) == 1
    assert result[0].id == "test-session-123"
    assert result[0].query == "hello world"
    assert result[0].result == "Hi there! How can I help?"
    assert result[0].duration_s == 3


def test_list_sessions_excludes_agent_files(temp_projects_dir: Path, sessions_client: SessionsClient) -> None:
    project_dir = temp_projects_dir / "-home-test"
    messages = [
        {
            "type": "user",
            "message": {"role": "user", "content": "test"},
            "timestamp": "2025-12-04T06:39:49.447Z",
        },
    ]
    _create_session_file(project_dir, "agent-abc123", messages)

    result = sessions_client.list_sessions(10)
    assert result == []


def test_list_sessions_respects_count_limit(temp_projects_dir: Path, sessions_client: SessionsClient) -> None:
    project_dir = temp_projects_dir / "-home-test"
    for i in range(5):
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": f"query {i}"},
                "timestamp": f"2025-12-0{i + 1}T06:39:49.447Z",
            },
        ]
        _create_session_file(project_dir, f"session-{i}", messages)

    result = sessions_client.list_sessions(2)
    assert len(result) == 2


def test_list_sessions_sorted_by_start_time_descending(
    temp_projects_dir: Path, sessions_client: SessionsClient
) -> None:
    project_dir = temp_projects_dir / "-home-test"
    messages_old = [
        {
            "type": "user",
            "message": {"role": "user", "content": "old query"},
            "timestamp": "2025-12-01T06:39:49.447Z",
        },
    ]
    messages_new = [
        {
            "type": "user",
            "message": {"role": "user", "content": "new query"},
            "timestamp": "2025-12-04T06:39:49.447Z",
        },
    ]
    _create_session_file(project_dir, "old-session", messages_old)
    _create_session_file(project_dir, "new-session", messages_new)

    result = sessions_client.list_sessions(10)
    assert len(result) == 2
    assert result[0].id == "new-session"
    assert result[1].id == "old-session"


def test_get_session_returns_session(temp_projects_dir: Path, sessions_client: SessionsClient) -> None:
    project_dir = temp_projects_dir / "-home-test"
    messages = [
        {
            "type": "user",
            "message": {"role": "user", "content": "hello"},
            "timestamp": "2025-12-04T06:39:49.447Z",
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi!"}]},
            "timestamp": "2025-12-04T06:39:52.447Z",
        },
    ]
    _create_session_file(project_dir, "test-session-456", messages)

    result = sessions_client.get_session("test-session-456")

    assert result is not None
    assert result.id == "test-session-456"
    assert len(result.messages) == 2


def test_get_session_not_found(sessions_client: SessionsClient) -> None:
    result = sessions_client.get_session("nonexistent-session")
    assert result is None
