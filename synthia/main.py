import logging
import os
import sys
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path

_t_process_start = _time.perf_counter()

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from google.adk.sessions import DatabaseSessionService
from loguru import logger
from openai import AsyncOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from synthia.agents.admin.client import create_admin_tools
from synthia.agents.episodic.client import create_episodic_tools
from synthia.agents.episodic.sync import EpisodicMemoryService
from synthia.agents.mcp import build_mcp_toolsets, prewarm_mcp_toolsets
from synthia.agents.memory.client import create_memory_tools
from synthia.agents.scheduler.client import create_scheduler_tools
from synthia.agents.skills import build_skill_toolset
from synthia.agents.skilltools.client import create_skilltools_tools
from synthia.helpers.pubsub import pubsub
from synthia.metrics import create_instrumentator
from synthia.migrations.runner import run_migrations
from synthia.routes.chat import router as chat_router
from synthia.routes.health import router as health_router
from synthia.routes.push import router as push_router
from synthia.routes.task import router as task_router
from synthia.service.chat import ChatService
from synthia.service.job_execution_repository import JobExecutionRepository
from synthia.service.models import AppStartup
from synthia.service.push import PushService
from synthia.service.session_repository import SessionRepository
from synthia.service.task import TaskService
from synthia.service.task_repository import TaskRepository
from synthia.telemetry import instrument_fastapi, loguru_otel_sink, setup_telemetry

load_dotenv()

setup_telemetry()

logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("uvicorn.error").disabled = True
logging.getLogger("uvicorn").disabled = True
logging.getLogger("LiteLLM").setLevel(logging.ERROR)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="DEBUG",
    colorize=True,
)
logger.add(loguru_otel_sink, level="DEBUG")


def _register_handlers(
    episodic_memory_service: EpisodicMemoryService, chat_service: ChatService, openai_client: AsyncOpenAI | None
):
    from synthia.agents.agent import Message, ResultDelta
    from synthia.agents.progress import ProgressAnalyzer
    from synthia.service.models import OutgoingImage, ProgressNotification

    pubsub.subscribe(Message, lambda message: logger.info(f"{message.render()}"))
    pubsub.subscribe(ProgressAnalyzer(openai_client))
    pubsub.subscribe(Message, episodic_memory_service.track_message)
    pubsub.subscribe(Message, chat_service.handle_message)
    pubsub.subscribe(ResultDelta, chat_service.handle_delta)
    pubsub.subscribe(ProgressNotification, chat_service.handle_progress)
    pubsub.subscribe(OutgoingImage, chat_service.handle_image)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_connection_string: str = "postgresql://postgres:postgres@pgvector:5432/vector_store"
    ollama_url: str | None = None
    claude_cwd: Path | None = None
    mcp_config_path: Path | None = Path("mcp_servers.json")
    vapid_private_key: str | None = None
    vapid_public_key: str | None = None


def create_app(config_overrides: Config | None = None) -> FastAPI:
    config = config_overrides or Config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            run_migrations(config.postgres_connection_string)

            db_pool = await asyncpg.create_pool(config.postgres_connection_string, min_size=2, max_size=10)

            memory_tools = await create_memory_tools(
                postgres_url=config.postgres_connection_string,
                ollama_url=config.ollama_url,
            )
            scheduler_tools, scheduler_service = create_scheduler_tools(config.postgres_connection_string)
            admin_tools = create_admin_tools()
            session_repository = await SessionRepository.create(config.postgres_connection_string)

            logger.info("Enabling episodic memory tools...")
            episodic_tools = create_episodic_tools(db_pool)

            job_execution_repo = JobExecutionRepository(db_pool)
            task_repository = TaskRepository(db_pool)
            skilltools = create_skilltools_tools(job_execution_repo)

            mcp_toolsets = build_mcp_toolsets(config.mcp_config_path)
            skill_toolset = build_skill_toolset(config.claude_cwd)

            tools: list = [
                *memory_tools,
                *scheduler_tools,
                *admin_tools,
                *skilltools,
                *mcp_toolsets,
            ]
            if skill_toolset:
                tools.append(skill_toolset)

            session_db_url = config.postgres_connection_string.replace("postgresql://", "postgresql+psycopg://")
            session_service = DatabaseSessionService(db_url=session_db_url)

            episodic_memory_service = EpisodicMemoryService(pool=db_pool, cwd=config.claude_cwd)

            chat_service = ChatService(db_pool, cwd=config.claude_cwd)
            await chat_service.initialize()
            app.state.chat_service = chat_service
            app.state.openai_client = AsyncOpenAI() if os.getenv("OPENAI_API_KEY") else None

            _register_handlers(episodic_memory_service, chat_service, app.state.openai_client)

            task_service = TaskService(
                tools=tools,
                session_repository=session_repository,
                session_service=session_service,
                cwd=config.claude_cwd,
                job_execution_repo=job_execution_repo,
                skill_toolset=skill_toolset,
                message_repository=chat_service.repository,
                task_repository=task_repository,
                front_tools=[*episodic_tools, *memory_tools, *scheduler_tools],
            )

            scheduler_service.start()

            app.state.task_service = task_service
            app.state.scheduler_service = scheduler_service
            if config.vapid_private_key and config.vapid_public_key:
                push_service = PushService(db_pool, config.vapid_private_key, config.vapid_public_key)
                app.state.push_service = push_service
            else:
                app.state.push_service = None
                logger.warning("VAPID keys not set — Web Push notifications disabled")

            await pubsub.start()

            await prewarm_mcp_toolsets(mcp_toolsets)

            _startup_duration = round(_time.perf_counter() - _t_process_start, 1)
            logger.bind(type="startup", duration_s=_startup_duration).info(f"Startup completed in {_startup_duration}s")

            await pubsub.publish(AppStartup())

            yield

            scheduler_service.shutdown()
            for toolset in mcp_toolsets:
                try:
                    await toolset.close()
                except Exception:
                    pass
            await pubsub.stop()
            await db_pool.close()
        except BaseException:
            logger.opt(exception=True).critical("Fatal error during lifespan")
            raise

    app = FastAPI(title="Synthia", description="FastAPI application with Google ADK integration", lifespan=lifespan)

    app.include_router(task_router)
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(push_router)

    _static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    instrumentator = create_instrumentator()
    instrumentator.instrument(app).expose(app)

    instrument_fastapi(app)

    return app


logger.info("starting Synthia")

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
