import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from synthia.agents.admin.client import create_admin_mcp_server
from synthia.agents.claude import ClaudeAgent
from synthia.agents.memory.client import create_memory_client, create_memory_mcp_server
from synthia.agents.scheduler.client import create_scheduler_mcp_server
from synthia.agents.scheduler.service import SchedulerService
from synthia.discord import Discord
from synthia.helpers.pubsub import pubsub
from synthia.service.models import TaskRequest, TaskResponse
from synthia.service.task import TaskService

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


def _register_handlers():
    from synthia.agents.claude import Message
    from synthia.agents.progress import analyze_progress
    from synthia.service.models import TaskCompletion

    pubsub.subscribe(Message, lambda message: logger.info(f"{message.render()}"))
    pubsub.subscribe(Message, analyze_progress)
    pubsub.subscribe(TaskCompletion, lambda c: None)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    memory_user: str
    discord_bot_token: str
    discord_users: str
    admin_user: str
    postgres_connection_string: str = ""

    @property
    def discord_users_map(self) -> dict[str, str]:
        if not self.discord_users:
            return {}
        return {
            user.strip(): channel_id.strip()
            for pair in self.discord_users.split(",")
            if ":" in pair
            for user, channel_id in [pair.split(":", 1)]
        }

    @property
    def admin_channel_id(self) -> str:
        channel_id = self.discord_users_map.get(self.admin_user)
        if not channel_id:
            raise ValueError(f"admin_user '{self.admin_user}' not found in discord_users")
        return channel_id


def create_app(config_overrides: Config | None = None) -> FastAPI:
    config = config_overrides or Config()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _register_handlers()

        memory_client = await create_memory_client()
        memory_mcp_server = create_memory_mcp_server(user=config.memory_user, memory_client=memory_client)

        scheduler_service = SchedulerService(postgres_url=config.postgres_connection_string)
        scheduler_mcp_server = create_scheduler_mcp_server(scheduler_service)

        admin_mcp_server = create_admin_mcp_server()

        claude_agent = ClaudeAgent(
            mcp_servers={
                "memory": memory_mcp_server,
                "scheduler": scheduler_mcp_server,
                "admin": admin_mcp_server,
            },
        )
        task_service = TaskService(claude_agent)

        scheduler_service.start()

        app.state.task_service = task_service
        app.state.scheduler_service = scheduler_service
        app.state.discord = Discord(
            config.discord_bot_token, config.discord_users_map, config.admin_channel_id, task_service
        )
        await app.state.discord.start()
        await pubsub.start()

        yield

        scheduler_service.shutdown()
        await app.state.discord.stop()
        await pubsub.stop()

    app = FastAPI(
        title="Synthia", description="FastAPI application with Claude Agent SDK integration", lifespan=lifespan
    )

    @app.post("/task", response_model=TaskResponse)
    async def task(request: TaskRequest) -> TaskResponse:
        task_service: TaskService = app.state.task_service
        try:
            response = await task_service.process_task(request, resume=request.resume)
            return response
        except asyncio.CancelledError:
            raise HTTPException(status_code=499, detail="Task was cancelled") from None

    @app.post("/stop")
    async def stop():
        task_service: TaskService = app.state.task_service
        await task_service.stop_current_task()

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app


logger.info("starting Synthia")

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
