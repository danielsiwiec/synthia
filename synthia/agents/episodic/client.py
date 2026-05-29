from collections.abc import Callable

import asyncpg

from synthia.agents.episodic.tools.search import create_search_tool
from synthia.agents.episodic.tools.show import create_show_tool


def create_episodic_tools(pool: asyncpg.Pool) -> list[Callable]:
    return [
        create_search_tool(pool),
        create_show_tool(pool),
    ]
