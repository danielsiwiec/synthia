from dotenv import load_dotenv

from output import parse

load_dotenv()


async def test_parse_happy_path():
    result = await parse(
        "4",
        {
            "type": "object",
            "properties": {"result": {"type": "number"}},
            "required": ["result"],
        },
    )

    assert result == {"result": 4}
    assert isinstance(result["result"], int)
