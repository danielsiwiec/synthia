## Running tests
uv run pytest ... -n auto --testmon

## Package management
always add and remove packages using uv add/uv remove

## Verifying changes
- run `make check` after all changes
- after every change run the tests with the smoke marker. Do not use testmon or xdist for smoke test
- run all tests only after larger code changes. When running all tests, add

## Code style
- never add comments or docstrings
- use `_` prefix for all internal functions and fields that are not consumed outside of the module

## Tests
- when writing tests, do not use any mocks or patches, unless instructed to