from typing import Any

from claude_agent_sdk import create_sdk_mcp_server


def create_image_mcp_server(thread_id: int) -> Any:
    from synthia.agents.image.tools.generate_image import create_generate_image_tool

    tools = [
        create_generate_image_tool(thread_id),
    ]
    return create_sdk_mcp_server(name="image", version="0.0.1", tools=tools)
