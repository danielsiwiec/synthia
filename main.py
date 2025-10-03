from typing import Any

import jsonschema
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from agents.task import Result, process_objective
from output import parse

load_dotenv()

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
    level="DEBUG",
)

app = FastAPI(title="Daimos", description="FastAPI application with Claude Agent SDK integration")


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


async def _process_messages(message_iterator) -> tuple[list[Any] | None, Result | None]:
    result_message = None
    trace_messages = []

    async for message in message_iterator:
        message_dict = {"type": type(message).__name__, "content": str(message)}
        if hasattr(message, "result"):
            message_dict["result"] = message.result
        if hasattr(message, "content"):
            message_dict["content"] = message.content
        trace_messages.append(message_dict)

        if isinstance(message, Result):
            result_message = message
            break

    return trace_messages, result_message


@app.post("/task", response_model=TaskResponse)
async def process_task(request: TaskRequest) -> TaskResponse:
    _validate_schema(request.response_schema)

    trace_messages, result_message = await _process_messages(process_objective(request.task))

    if not result_message:
        raise HTTPException(
            status_code=408,
            detail="Timeout: No ResultMessage received within expected time",
        )

    final_result = result_message.result
    if request.response_schema is not None:
        final_result = await parse(result_message.result, request.response_schema)

    return TaskResponse(result=final_result, trace=trace_messages if request.trace else None)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
