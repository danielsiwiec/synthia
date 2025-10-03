from typing import Any

import jsonschema
from claude_agent_sdk import ResultMessage
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.task import process_objective
from output import parse

load_dotenv()

app = FastAPI(title="Daimos", description="FastAPI application with Claude Agent SDK integration")


class TaskRequest(BaseModel):
    task: str
    trace: bool = False
    response_schema: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    result: Any
    trace: list[Any] | None = None


@app.post("/task", response_model=TaskResponse)
async def process_task(request: TaskRequest) -> TaskResponse:
    if request.response_schema is not None:
        try:
            jsonschema.Draft7Validator.check_schema(request.response_schema)
        except jsonschema.exceptions.SchemaError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON schema: {str(e)}") from e

    result_message = None
    trace_messages = [] if request.trace else None

    async for message in process_objective(request.task):
        if request.trace:
            message_dict = {"type": type(message).__name__, "content": str(message)}
            if hasattr(message, "result"):
                message_dict["result"] = message.result
            if hasattr(message, "content"):
                message_dict["content"] = message.content
            trace_messages.append(message_dict)

        if isinstance(message, ResultMessage):
            result_message = message
            break

    if not result_message:
        raise HTTPException(
            status_code=408,
            detail="Timeout: No ResultMessage received within expected time",
        )

    final_result = result_message.result
    if request.response_schema is not None:
        final_result = await parse(result_message.result, request.response_schema)

    return TaskResponse(result=final_result, trace=trace_messages)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
