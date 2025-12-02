from typing import Any

from claude_agent_sdk import create_sdk_mcp_server


def create_admin_mcp_server() -> Any:
    from synthia.agents.admin.tools.notify import create_notify_tool

    tools = [
        create_notify_tool(),
    ]
    return create_sdk_mcp_server(name="admin", version="0.0.1", tools=tools)
