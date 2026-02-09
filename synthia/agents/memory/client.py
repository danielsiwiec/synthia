from typing import Any

from claude_agent_sdk import create_sdk_mcp_server
from mem0 import AsyncMemory

OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_EMBEDDING_DIMS = 768


async def create_memory_mcp_server(user: str, postgres_url: str, ollama_url: str | None = None) -> Any:
    from synthia.agents.memory.tools.add_memory import create_add_memory_tool
    from synthia.agents.memory.tools.delete_memory import create_delete_memory_tool
    from synthia.agents.memory.tools.search_memories import create_search_memories_tool

    config: dict = {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": postgres_url,
            },
        },
    }
    if ollama_url:
        config["embedder"] = {
            "provider": "ollama",
            "config": {
                "model": OLLAMA_EMBEDDING_MODEL,
                "ollama_base_url": ollama_url,
            },
        }
        config["vector_store"]["config"]["embedding_model_dims"] = OLLAMA_EMBEDDING_DIMS
    memory_client = await AsyncMemory.from_config(config)

    tools = [
        create_add_memory_tool(user, memory_client),
        create_delete_memory_tool(user, memory_client),
        create_search_memories_tool(user, memory_client),
    ]
    return create_sdk_mcp_server(name="memory", version="0.0.1", tools=tools)
