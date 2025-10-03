from typing import Any

import jsonschema
from fastapi import HTTPException


def validate_schema(schema: dict[str, Any] | None) -> None:
    if schema is not None:
        try:
            jsonschema.Draft7Validator.check_schema(schema)
        except jsonschema.exceptions.SchemaError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON schema: {str(e)}") from e
