from collections.abc import Callable

from synthia.agents.tools import error_response, success_response
from synthia.helpers.pubsub import pubsub
from synthia.service.models import AdminNotification


def create_notify_tool() -> Callable:
    async def notify(message: str) -> str:
        """Send a push notification to the user. Use this to alert about important events.

        Args:
            message: The notification message to send to the admin.
        """
        try:
            await pubsub.publish(AdminNotification(content=message))
            return success_response("Notification sent")
        except Exception as error:
            return error_response(f"Error sending notification: {error}")

    return notify
