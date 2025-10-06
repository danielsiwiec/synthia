import logging
import sys
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from daimos.agents.claude import Message, Result, run
from daimos.agents.helpers.message_printer import Summarizer, log_message
from daimos.events.events import EventEmitter, EventType
from daimos.helpers.schema import validate_schema
from daimos.output import parse

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

app = FastAPI(title="Daimos", description="FastAPI application with Claude Agent SDK integration")
logger.info("Starting Daimos")


class TaskRequest(BaseModel):
    task: str
    response_schema: dict[str, Any] | None = None
    resume: str | None = None


class TaskResponse(BaseModel):
    result: Any
    session_id: str


@app.post("/task", response_model=TaskResponse)
async def process_task(request: TaskRequest) -> TaskResponse:
    validate_schema(request.response_schema)

    event_emitter = EventEmitter[Message]()
    event_emitter.on(EventType.TASK_AGENT_MESSAGE, log_message)

    summarizer = Summarizer()
    event_emitter.on(EventType.TASK_AGENT_MESSAGE, summarizer.process_message)
    result_message = None
    async for message in run(objective=request.task, resume=request.resume):
        await event_emitter.emit(EventType.TASK_AGENT_MESSAGE, message)
        if isinstance(message, Result):
            result_message = message

    if not result_message:
        raise HTTPException(
            status_code=408,
            detail="Timeout: No ResultMessage received within expected time",
        )

    result = (
        await parse(result_message.result, request.response_schema)
        if request.response_schema
        else result_message.result
    )
    return TaskResponse(result=result, session_id=result_message.session_id)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
