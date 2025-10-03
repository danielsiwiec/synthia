# Daimos

A FastAPI application with Claude Agent SDK integration for processing tasks.

## Quick Start

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Run the application:**
   ```bash
   make start
   # or for development with auto-reload:
   make dev
   ```

3. **Test the API:**
   ```bash
   curl -X POST "http://localhost:8003/task" \
        -H "Content-Type: application/json" \
        -d '{"task": "list files in current folder, then for each file smaller than 1MB count the number of words 'task' in it", "response_schema": {"type": "object", "properties": {"total_count": {"type": "integer"}}, "required": ["total_count"]}}'
   ```

## API Documentation

Once running, visit `http://localhost:8003/docs` for interactive API documentation.

## Documentation

See [agents.md](agents.md) for detailed documentation about the application architecture and usage.

