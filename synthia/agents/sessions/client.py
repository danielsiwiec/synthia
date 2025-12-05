import json
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server
from pydantic import BaseModel


class SessionMeta(BaseModel):
    id: str
    query: str
    result: str
    start_time: datetime
    duration_s: int


class Session(BaseModel):
    id: str
    messages: list[dict[str, Any]]


class SessionsClient:
    def __init__(self, projects_dir: Path):
        self._projects_dir = projects_dir

    def _get_session_files(self) -> list[Path]:
        session_files = []
        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for jsonl_file in project_dir.glob("*.jsonl"):
                if jsonl_file.name.startswith("agent-"):
                    continue
                session_files.append(jsonl_file)
        return session_files

    def _parse_session_meta(self, session_file: Path) -> SessionMeta | None:
        messages = self._read_messages(session_file)
        if not messages:
            return None

        session_id = session_file.stem
        query = ""
        result = ""
        start_time = None
        end_time = None

        for msg in messages:
            if msg.get("type") == "user" and not query:
                message_content = msg.get("message", {})
                content = message_content.get("content", "")
                if isinstance(content, str):
                    query = content
                timestamp = msg.get("timestamp")
                if timestamp and start_time is None:
                    start_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            if msg.get("type") == "assistant":
                message_content = msg.get("message", {})
                content_blocks = message_content.get("content", [])
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            result = block.get("text", "")
                timestamp = msg.get("timestamp")
                if timestamp:
                    end_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if start_time is None:
            return None

        duration_s = 0
        if end_time and start_time:
            duration_s = int((end_time - start_time).total_seconds())

        return SessionMeta(
            id=session_id,
            query=query[:200] if query else "",
            result=result[:500] if result else "",
            start_time=start_time,
            duration_s=duration_s,
        )

    def _read_messages(self, session_file: Path) -> list[dict[str, Any]]:
        messages = []
        with session_file.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return messages

    def list_sessions(self, count: int) -> list[SessionMeta]:
        session_files = self._get_session_files()
        session_metas = []
        for session_file in session_files:
            meta = self._parse_session_meta(session_file)
            if meta:
                session_metas.append(meta)

        session_metas.sort(key=lambda x: x.start_time, reverse=True)
        return session_metas[:count]

    def get_session(self, session_id: str) -> Session | None:
        for session_file in self._get_session_files():
            if session_file.stem == session_id:
                messages = self._read_messages(session_file)
                return Session(id=session_id, messages=messages)
        return None


def create_sessions_mcp_server(projects_dir: Path) -> Any:
    from synthia.agents.sessions.tools.get_session import create_get_session_tool
    from synthia.agents.sessions.tools.list_sessions import create_list_sessions_tool

    sessions_client = SessionsClient(projects_dir)

    tools = [
        create_list_sessions_tool(sessions_client),
        create_get_session_tool(sessions_client),
    ]
    return create_sdk_mcp_server(name="sessions", version="0.0.1", tools=tools)
