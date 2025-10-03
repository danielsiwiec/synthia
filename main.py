import sys
from typing import Any

import jsonschema
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from agents.helpers.events import EventEmitter, EventType
from agents.helpers.message_printer import log_message
from agents.task import Result, process_objective
from output import parse

load_dotenv()

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

    event_emitter = EventEmitter()
    event_emitter.on(EventType.MESSAGE_TRANSFORMED, log_message)
    trace = []
    result_message = None
    async for message in process_objective(request.task, event_emitter):
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
