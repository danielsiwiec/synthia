from typing import Any

from claude_agent_sdk import create_sdk_mcp_server


def create_image_mcp_server() -> Any:
    from synthia.agents.image.tools.generate_image import generate_image

    tools = [generate_image]
    return create_sdk_mcp_server(name="image", version="0.0.1", tools=tools)
