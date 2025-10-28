from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel


async def parse_from_schema(input: str, schema: dict[str, Any]) -> dict[str, Any]:
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # type: ignore[arg-type]

    structured_schema = {
        "title": "ParsedResult",
        "description": "The parsed result matching the provided schema",
        **schema,
    }
    return await model.with_structured_output(structured_schema).ainvoke(
        f"Parse the following input into the given schema: {input}"
    )


async def parse_from_type[T: BaseModel](input: str, schema: type[T]) -> T:
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # type: ignore[arg-type]

    return await model.with_structured_output(schema).ainvoke(
        f"Parse the following input into the given format: {input}"
    )
