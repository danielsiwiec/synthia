import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger
from mem0 import AsyncMemory

import synthia.helpers.debug  # noqa: F401
from synthia.agents.claude import ClaudeAgent
from synthia.agents.memory.client import create_memory_mcp_server
from synthia.helpers.pubsub import pubsub
from synthia.service.task import TaskRequest, TaskResponse, TaskService
from synthia.telegram import Telegram

load_dotenv()

logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("uvicorn.error").disabled = True
logging.getLogger("uvicorn").disabled = True

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="DEBUG",
    colorize=True,
)


class Config(TypedDict, total=False):
    memory_user: str
    telegram_bot_token: str
    telegram_chat_id: str


def _get_config(overrides: Config | None = None) -> Config:
    config: Config = {
        "memory_user": os.environ.get("MEMORY_USER", ""),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    }
    if overrides:
        config.update(overrides)
    return config


def create_app(config_overrides: Config | None = None) -> FastAPI:
    config = _get_config(config_overrides)

    memory_client = AsyncMemory()
    memory_mcp_server = create_memory_mcp_server(user=config["memory_user"], memory_client=memory_client)
    claude_agent = ClaudeAgent(user=config["memory_user"], memory_mcp_server=memory_mcp_server)
    task_service = TaskService(claude_agent)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.telegram = Telegram(config["telegram_bot_token"], config["telegram_chat_id"], task_service)
        await app.state.telegram.start()
        await pubsub.start()

        yield

        await app.state.telegram.stop()
        await pubsub.stop()

    app = FastAPI(
        title="Synthia", description="FastAPI application with Claude Agent SDK integration", lifespan=lifespan
    )

    @app.post("/task", response_model=TaskResponse)
    async def task(request: TaskRequest) -> TaskResponse:
        response = await task_service.process_task(request, resume=request.resume)
        return response

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app


logger.info("starting Synthia")

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
