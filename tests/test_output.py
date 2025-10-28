from dotenv import load_dotenv

from synthia.output import parse_from_schema

load_dotenv()


async def test_parse_happy_path():
    result = await parse_from_schema(
        "answer is4",
        {
            "type": "object",
            "properties": {"result": {"type": "number"}},
            "required": ["result"],
        },
    )

    assert result == {"result": 4}
    assert isinstance(result["result"], int)
