## Running tests
uv run pytest ... -n auto --testmon

## Package management
Always add and remove packages using uv add/uv remove

## Verifying changes
- After every change run the tests with the smoke marker. Do not use testmon or xdist for smoke test
- Run all tests only after larger code changes. When running all tests, add

## Code style
Never add comments