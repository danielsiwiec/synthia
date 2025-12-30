---
description: Update project dependencies
---

# Steps:
- Perform these steps for each package in pyproject.toml:
  - Remove it and add it back with `uv`
  - If the `uv.lock` changed, run all tests with `uv run pytest tests\ -n auto` and checks with `make check`
  - If the test pass, proceed to the next dependency. If they fail, address the problem