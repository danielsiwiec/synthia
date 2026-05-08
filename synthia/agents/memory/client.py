from typing import Any

from claude_agent_sdk import create_sdk_mcp_server
from mem0 import AsyncMemory

OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_EMBEDDING_DIMS = 768


def _mem0_config(postgres_url: str, ollama_url: str | None = None) -> dict:
    config: dict = {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": postgres_url,
            },
        },
    }
    if ollama_url:
        ollama_config = {
            "provider": "ollama",
            "config": {
                "model": OLLAMA_EMBEDDING_MODEL,
                "ollama_base_url": ollama_url,
            },
        }
        config["embedder"] = ollama_config
        config["llm"] = ollama_config
        config["vector_store"]["config"]["embedding_model_dims"] = str(OLLAMA_EMBEDDING_DIMS)
    return config


async def create_memory_mcp_server(postgres_url: str, ollama_url: str | None = None) -> Any:
    from synthia.agents.memory.tools.add_memory import create_add_memory_tool
    from synthia.agents.memory.tools.delete_memory import create_delete_memory_tool
    from synthia.agents.memory.tools.search_memories import create_search_memories_tool

    memory_client = AsyncMemory.from_config(_mem0_config(postgres_url, ollama_url))

    tools = [
        create_add_memory_tool(memory_client),
        create_delete_memory_tool(memory_client),
        create_search_memories_tool(memory_client),
    ]
    return create_sdk_mcp_server(name="memory", version="0.0.1", tools=tools)
