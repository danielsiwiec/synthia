import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from claude_agent_sdk.types import McpHttpServerConfig
from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger
from openai import AsyncOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from synthia.agents.admin.client import create_admin_mcp_server
from synthia.agents.episodic.client import create_episodic_mcp_server
from synthia.agents.episodic.sync import EpisodicMemoryService
from synthia.agents.memory.client import create_memory_mcp_server
from synthia.agents.pool import ClaudeAgentPool
from synthia.agents.scheduler.client import create_scheduler_mcp_server
from synthia.discord.client import Discord
from synthia.helpers.pubsub import pubsub
from synthia.metrics import create_instrumentator
from synthia.migrations.runner import run_migrations
from synthia.routes.audio import router as audio_router
from synthia.routes.health import router as health_router
from synthia.routes.task import router as task_router
from synthia.routes.voice import mount_static
from synthia.routes.voice import router as voice_router
from synthia.service.session_repository import SessionRepository
from synthia.service.task import TaskService
from synthia.telemetry import instrument_fastapi, loguru_otel_sink, setup_telemetry

load_dotenv()

setup_telemetry()

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
logger.add(loguru_otel_sink, level="DEBUG")


def _register_handlers(episodic_memory_service: EpisodicMemoryService):
    from synthia.agents.agent import Message
    from synthia.agents.progress import analyze_progress

    pubsub.subscribe(Message, lambda message: logger.info(f"{message.render()}"))
    pubsub.subscribe(Message, analyze_progress)
    pubsub.subscribe(Message, episodic_memory_service.track_message)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    memory_user: str
    discord_bot_token: str
    discord_channels: str
    admin_channel: str
    postgres_connection_string: str
    claude_cwd: Path | None = None
    enable_claude_pool: bool = True

    @property
    def discord_channels_list(self) -> list[str]:
        return [channel.strip() for channel in self.discord_channels.split(",")]


def create_app(config_overrides: Config | None = None) -> FastAPI:
    config = config_overrides or Config()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        run_migrations(config.postgres_connection_string)

        db_pool = await asyncpg.create_pool(config.postgres_connection_string, min_size=2, max_size=10)

        memory_mcp_server = await create_memory_mcp_server(
            user=config.memory_user, postgres_url=config.postgres_connection_string
        )
        scheduler_mcp_server, scheduler_service = create_scheduler_mcp_server(config.postgres_connection_string)
        admin_mcp_server = create_admin_mcp_server()
        session_repository = await SessionRepository.create(config.postgres_connection_string)

        logger.info("Enabling episodic memory MCP server...")
        episodic_mcp_server = create_episodic_mcp_server(db_pool)

        mcp_servers = {
            "memory": memory_mcp_server,
            "scheduler": scheduler_mcp_server,
            "admin": admin_mcp_server,
            "episodic": episodic_mcp_server,
            "google": McpHttpServerConfig(type="http", url="http://google-mcp:8000/mcp"),
        }

        if os.getenv("GEMINI_API_KEY"):
            from synthia.agents.image.client import create_image_mcp_server

            logger.info("Enabling image MCP server...")
            mcp_servers["image"] = create_image_mcp_server()

        agent_pool = await ClaudeAgentPool.create(
            mcp_servers=mcp_servers, cwd=config.claude_cwd, enabled=config.enable_claude_pool
        )

        episodic_memory_service = EpisodicMemoryService(pool=db_pool, cwd=config.claude_cwd)

        _register_handlers(episodic_memory_service)

        task_service = TaskService(agent_pool, session_repository)

        scheduler_service.start()

        app.state.task_service = task_service
        app.state.agent_pool = agent_pool
        app.state.scheduler_service = scheduler_service
        app.state.openai_client = AsyncOpenAI()
        app.state.discord = Discord(config.discord_bot_token, config.discord_channels_list, config.admin_channel)
        await app.state.discord.start()
        await pubsub.start()

        yield

        scheduler_service.shutdown()
        await app.state.discord.stop()
        await pubsub.stop()
        await agent_pool.shutdown()
        await db_pool.close()

    app = FastAPI(
        title="Synthia", description="FastAPI application with Claude Agent SDK integration", lifespan=lifespan
    )

    app.include_router(task_router)
    app.include_router(audio_router)
    app.include_router(health_router)
    app.include_router(voice_router)
    mount_static(app)

    instrumentator = create_instrumentator()
    instrumentator.instrument(app).expose(app)

    instrument_fastapi(app)

    return app


logger.info("starting Synthia")

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
