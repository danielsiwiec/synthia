from collections.abc import Callable


def create_admin_tools() -> list[Callable]:
    from synthia.agents.admin.tools.notify import create_notify_tool

    return [
        create_notify_tool(),
    ]
