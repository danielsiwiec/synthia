import json
from pathlib import Path

from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from loguru import logger
from mcp import StdioServerParameters


def _build_toolset(name: str, server_config: dict) -> McpToolset | None:
    server_type = server_config.get("type")

    if server_type in ("http", "streamable-http"):
        return McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=server_config["url"],
                headers=server_config.get("headers"),
            ),
            tool_name_prefix=name,
        )

    if server_type == "sse":
        return McpToolset(
            connection_params=SseConnectionParams(
                url=server_config["url"],
                headers=server_config.get("headers"),
            ),
            tool_name_prefix=name,
        )

    if server_type == "stdio":
        return McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=server_config["command"],
                    args=server_config.get("args", []),
                    env=server_config.get("env"),
                )
            ),
            tool_name_prefix=name,
        )

    logger.warning(f"Unknown MCP server type '{server_type}' for '{name}', skipping")
    return None


def build_mcp_toolsets(mcp_config_path: Path | None) -> list[McpToolset]:
    if not mcp_config_path or not mcp_config_path.exists():
        return []

    config = json.loads(mcp_config_path.read_text())
    toolsets: list[McpToolset] = []
    for name, server_config in config.get("mcpServers", {}).items():
        logger.info(f"Loading MCP server: {name}")
        toolset = _build_toolset(name, server_config)
        if toolset:
            toolsets.append(toolset)
    return toolsets
