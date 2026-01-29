## Running tests
uv run pytest ... -n auto --testmon

## Package management
- always add and remove packages using uv add/uv remove
- to update dependencies, use the `/update-dependencies` skill

## Verifying changes
- run `make check` after all changes
- after every change run the tests with the smoke marker. Do not use testmon or xdist for smoke test
- run all tests only after larger code changes
- when running multiple tests for verification, use xdist with `-n auto`

## Code style
- never add comments or docstrings
- use `_` prefix for all internal functions and fields that are not consumed outside of the module

## Tests
- when writing tests, do not use any mocks or patches, unless instructed to

## Additional resources
IMPORTANT: review extras/extra.md for additional instructions if it exists
