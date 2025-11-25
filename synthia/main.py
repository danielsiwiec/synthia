import logging
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

import synthia.agents.progress  # noqa: F401
import synthia.helpers.debug  # noqa: F401
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
        result = {}
        for pair in self.telegram_users.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if ":" not in pair:
                continue
            user, chat_id = pair.split(":", 1)
            result[user.strip()] = chat_id.strip()
        return result

    @property
    def admin_chat_id(self) -> str:
        users_map = self.telegram_users_map
        chat_id = users_map.get(self.admin_user)
        if not chat_id:
            raise ValueError(f"admin_user '{self.admin_user}' not found in telegram_users")
        return chat_id


def create_app(config_overrides: Config | None = None) -> FastAPI:
    if config_overrides:
        config = config_overrides
    else:
        config = Config()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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

        try:
            scheduler_service.shutdown()
        except Exception:
            pass
        try:
            await app.state.telegram.stop()
        except Exception:
            pass
        try:
            await pubsub.stop()
        except Exception:
            pass

    app = FastAPI(
        title="Synthia", description="FastAPI application with Claude Agent SDK integration", lifespan=lifespan
    )

    @app.post("/task", response_model=TaskResponse)
    async def task(request: TaskRequest) -> TaskResponse:
        task_service: TaskService = app.state.task_service
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
