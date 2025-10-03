import logging
import sys
from typing import Any

import jsonschema
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from agents.claude import Message, Result, run
from agents.helpers.events import EventEmitter, EventType
from agents.helpers.message_printer import Summarizer, log_message
from output import parse

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
    trace: bool = False
    response_schema: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    result: Any
    trace: list[Any] | None = None


def _validate_schema(schema: dict[str, Any] | None) -> None:
    if schema is not None:
        try:
            jsonschema.Draft7Validator.check_schema(schema)
        except jsonschema.exceptions.SchemaError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON schema: {str(e)}") from e


@app.post("/task", response_model=TaskResponse)
async def process_task(request: TaskRequest) -> TaskResponse:
    _validate_schema(request.response_schema)

    event_emitter = EventEmitter[Message]()
    event_emitter.on(EventType.TASK_AGENT_MESSAGE, log_message)

    summarizer = Summarizer()
    event_emitter.on(EventType.TASK_AGENT_MESSAGE, summarizer.process_message)
    trace = []
    result_message = None
    async for message in run(request.task):
        await event_emitter.emit(EventType.TASK_AGENT_MESSAGE, message)
        trace.append(message)
        if isinstance(message, Result):
            result_message = message

    if not result_message:
        raise HTTPException(
            status_code=408,
            detail="Timeout: No ResultMessage received within expected time",
        )

    final_result = result_message.result
    if request.response_schema is not None:
        final_result = await parse(result_message.result, request.response_schema)

    return TaskResponse(result=final_result, trace=trace if request.trace else None)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
