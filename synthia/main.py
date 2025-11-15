import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger

import synthia.helpers.debug  # noqa: F401
from synthia.agents.agents import TaskAgentException
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

logger.info("Starting Synthia")

task_service = TaskService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.telegram = Telegram(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], task_service)
    await app.state.telegram.start()
    await pubsub.start()

    yield

    await app.state.telegram.stop()
    await pubsub.stop()


app = FastAPI(title="Synthia", description="FastAPI application with Claude Agent SDK integration", lifespan=lifespan)


@app.post("/task", response_model=TaskResponse)
async def task(request: TaskRequest) -> TaskResponse:
    try:
        response = await task_service.process_task(request, resume=request.resume)
        return response
    except TaskAgentException as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
