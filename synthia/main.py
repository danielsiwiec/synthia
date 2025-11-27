import asyncio
import logging
import sys
from contextlib import asynccontextmanager, suppress

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from synthia.agents.claude import ClaudeAgent
from synthia.agents.memory.client import create_memory_client, create_memory_mcp_server
from synthia.agents.scheduler.client import create_scheduler_mcp_server
from synthia.agents.scheduler.service import SchedulerService
from synthia.helpers.pubsub import pubsub
from synthia.service.models import TaskRequest, TaskResponse
from synthia.service.task import TaskService
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
    telegram_bot_token: str
    telegram_users: str
    admin_user: str
    postgres_connection_string: str = ""

    @property
    def telegram_users_map(self) -> dict[str, str]:
        if not self.telegram_users:
            return {}
        return {
            user.strip(): chat_id.strip()
            for pair in self.telegram_users.split(",")
            if ":" in pair
            for user, chat_id in [pair.split(":", 1)]
        }

    @property
    def admin_chat_id(self) -> str:
        chat_id = self.telegram_users_map.get(self.admin_user)
        if not chat_id:
            raise ValueError(f"admin_user '{self.admin_user}' not found in telegram_users")
        return chat_id


def create_app(config_overrides: Config | None = None) -> FastAPI:
    config = config_overrides or Config()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _register_handlers()

        memory_client = await create_memory_client()
        memory_mcp_server = create_memory_mcp_server(user=config.memory_user, memory_client=memory_client)

        scheduler_service = SchedulerService(postgres_url=config.postgres_connection_string)
        scheduler_mcp_server = create_scheduler_mcp_server(scheduler_service)

        claude_agent = ClaudeAgent(
            user=config.memory_user,
            mcp_servers={
                "memory": memory_mcp_server,
                "scheduler": scheduler_mcp_server,
            },
        )
        task_service = TaskService(claude_agent)

        scheduler_service.start()

        app.state.task_service = task_service
        app.state.scheduler_service = scheduler_service
        app.state.telegram = Telegram(
            config.telegram_bot_token, config.telegram_users_map, config.admin_chat_id, task_service
        )
        await app.state.telegram.start()
        await pubsub.start()

        yield

        with suppress(Exception):
            scheduler_service.shutdown()
        with suppress(Exception):
            await app.state.telegram.stop()
        with suppress(Exception):
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
