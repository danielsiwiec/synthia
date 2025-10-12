import logging
import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger

from daimos.agents.agents import TaskAgentException
from daimos.agents.claude import Message
from daimos.agents.helpers.message_printer import Summarizer
from daimos.helpers.events import EventEmitter, EventType
from daimos.service.task import TaskRequest, TaskResponse, TaskService
from daimos.telegram import Telegram

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

summarizer = Summarizer()
logger.info("Starting Daimos")
event_emitter = EventEmitter[Message]()
event_emitter.on(EventType.TASK_AGENT_MESSAGE, lambda message: logger.info(f"{message.render()}"))
event_emitter.on(EventType.TASK_AGENT_MESSAGE, summarizer.process_message)
task_service = TaskService(event_emitter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
    app.state.telegram = Telegram(telegram_token, os.environ["TELEGRAM_CHAT_ID"], task_service)
    await app.state.telegram.start()

    yield

    await app.state.telegram.stop()


app = FastAPI(title="Daimos", description="FastAPI application with Claude Agent SDK integration", lifespan=lifespan)


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
