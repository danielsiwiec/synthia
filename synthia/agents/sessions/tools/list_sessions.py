import json
from typing import Any

from claude_agent_sdk import tool

from synthia.agents.sessions.client import SessionsClient
from synthia.agents.tools import error_response, success_response


def create_list_sessions_tool(sessions_client: SessionsClient):
    @tool(
        "list-sessions",
        "List recent Claude Code sessions with metadata including query, result summary, start time, and duration.",
        {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of sessions to return (default 10)",
                    "default": 10,
                },
            },
            "required": [],
        },
    )
    async def list_sessions(args: dict[str, Any]) -> dict[str, Any]:
        count = args.get("count", 10)
        try:
            sessions = sessions_client.list_sessions(count)
            sessions_data = [s.model_dump(mode="json") for s in sessions]
            return success_response(json.dumps(sessions_data, indent=2))
        except Exception as error:
            return error_response(f"Error listing sessions: {error}")

    return list_sessions
