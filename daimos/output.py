from typing import Any

from langchain_openai import ChatOpenAI


async def parse(input: str, schema: dict[str, Any]) -> dict[str, Any]:
    structured_schema = {
        "title": "ParsedResult",
        "description": "The parsed result matching the provided schema",
        **schema,
    }

    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # type: ignore[arg-type]

    return await model.with_structured_output(structured_schema).ainvoke(
        f"Parse the following input into the given schema: {input}"
    )
