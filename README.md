# Synthia - Your AI Assistant That Actually Works

**Perfect memory. Smarter every day. Runs 24/7.**

## Capabilities

- Factual memory
- Conversation memory
- Built-in skills
- Scheduled tasks
- Create skills on the go

## Quick Start

### Prerequisites

- Docker & Docker Compose

### Option 1. Use Anthropic API key

Copy `.env.template` to `.env` and set `ANTHROPIC_API_KEY`

### Option 2. Use your existing Claude Code plan

1. Start Synthia (see below)
2. Run `docker exec -it synthia claude`
3. Run `/login` and follow instructions

### Start

`docker compose up -d`

Open http://localhost:8003/chat

## Integrations

### MCP

Custom MCP servers can be added via `mcp_servers.json` in the project root. The file follows the standard Claude Code MCP server format:

```json
{
  "mcpServers": {
    "my-server": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    },
    "my-stdio-server": {
      "type": "stdio",
      "command": "npx",
      "args": ["@example/mcp-server"],
      "env": {
        "API_KEY": "..."
      }
    }
  }
}
```

Then, add a volume in `docker-compose.yaml`:

`- ./mcp_servers.json:/home/synthia/workdir/mcp_servers.json`