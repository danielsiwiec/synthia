import json
from typing import Any

from claude_agent_sdk import tool

from synthia.agents.sessions.client import SessionsClient
from synthia.agents.tools import error_response, success_response


def create_get_session_tool(sessions_client: SessionsClient):
    @tool(
        "get-session",
        "Get the full details of a specific Claude Code session including all messages.",
        {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The session ID to retrieve",
                },
            },
            "required": ["id"],
        },
    )
    async def get_session(args: dict[str, Any]) -> dict[str, Any]:
        session_id = args["id"]
        try:
            session = sessions_client.get_session(session_id)
            if session is None:
                return error_response(f"Session not found: {session_id}")
            return success_response(json.dumps(session.model_dump(mode="json"), indent=2))
        except Exception as error:
            return error_response(f"Error getting session: {error}")

    return get_session
