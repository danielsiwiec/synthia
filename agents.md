## Running tests
uv run pytest ... -n auto --testmon

## Package management
always add and remove packages using uv add/uv remove

## Verifying changes
- run `make check` after all changes
- after every change run the tests with the smoke marker. Do not use testmon or xdist for smoke test
- run all tests only after larger code changes. When running all tests, add
- when running multiple tests for verification, use xdist with `-n auto`

## Code style
- never add comments or docstrings
- use `_` prefix for all internal functions and fields that are not consumed outside of the module

## Tests
- when writing tests, do not use any mocks or patches, unless instructed to

## Deploy and verify
- run `make up`
- check synthia's docker compose logs
- use the task endpoint to say 'hello'
- confirm the response is 200
- check logs again for errors