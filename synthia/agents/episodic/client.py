from typing import Any

import asyncpg
from claude_agent_sdk import create_sdk_mcp_server

from synthia.agents.episodic.tools.search import create_search_tool
from synthia.agents.episodic.tools.show import create_show_tool


def create_episodic_mcp_server(pool: asyncpg.Pool) -> Any:
    tools = [
        create_search_tool(pool),
        create_show_tool(pool),
    ]

    return create_sdk_mcp_server(name="episodic", version="0.1.0", tools=tools)
