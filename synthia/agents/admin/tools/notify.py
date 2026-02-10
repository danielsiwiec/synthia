from typing import Any

from claude_agent_sdk import tool

from synthia.agents.tools import error_response, success_response
from synthia.helpers.pubsub import pubsub
from synthia.service.models import AdminNotification


def create_notify_tool():
    @tool(
        "notify",
        "Send a push notification to the user. Use this to alert about important events.",
        {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The notification message to send to the admin",
                },
            },
            "required": ["message"],
        },
    )
    async def notify(args: dict[str, Any]) -> dict[str, Any]:
        try:
            await pubsub.publish(AdminNotification(content=args["message"]))
            return success_response("Notification sent")
        except Exception as error:
            return error_response(f"Error sending notification: {error}")

    return notify
