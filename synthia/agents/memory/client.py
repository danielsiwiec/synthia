import os
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server
from mem0 import AsyncMemory


async def create_memory_client() -> AsyncMemory:
    connection_string = os.environ.get("POSTGRES_CONNECTION_STRING", "")

    config = {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": connection_string,
            },
        }
    }

    return await AsyncMemory.from_config(config)


def create_memory_mcp_server(user: str, memory_client: AsyncMemory) -> Any:
    from synthia.agents.memory.tools.add_memory import create_add_memory_tool
    from synthia.agents.memory.tools.search_memories import create_search_memories_tool

    tools = [create_add_memory_tool(user, memory_client), create_search_memories_tool(user, memory_client)]
    return create_sdk_mcp_server(name="memory", version="0.0.1", tools=tools)
