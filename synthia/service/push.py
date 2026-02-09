import json

import asyncpg
from loguru import logger
from pywebpush import WebPushException, webpush

from synthia.helpers.pubsub import pubsub
from synthia.service.models import AdminNotification, AppStartup


class PushService:
    def __init__(self, pool: asyncpg.Pool, vapid_private_key: str, vapid_public_key: str):
        self._pool = pool
        self._vapid_private_key = vapid_private_key
        self._vapid_public_key = vapid_public_key
        pubsub.subscribe(AppStartup, self._handle_startup)
        pubsub.subscribe(AdminNotification, self._handle_admin_notification)

    @property
    def vapid_public_key(self) -> str:
        return self._vapid_public_key

    async def save_subscription(self, endpoint: str, p256dh: str, auth: str):
        await self._pool.execute(
            """
            INSERT INTO push_subscriptions (endpoint, keys_p256dh, keys_auth)
            VALUES ($1, $2, $3)
            ON CONFLICT (endpoint) DO UPDATE SET keys_p256dh = $2, keys_auth = $3
            """,
            endpoint,
            p256dh,
            auth,
        )

    async def _handle_startup(self, _event: AppStartup):
        await self._send_to_all("Synthia connected 👋")

    async def _handle_admin_notification(self, notification: AdminNotification):
        await self._send_to_all(notification.content, title="Job Complete")

    async def _send_to_all(self, message: str, title: str | None = None):
        rows = await self._pool.fetch("SELECT endpoint, keys_p256dh, keys_auth FROM push_subscriptions")
        if not rows:
            return

        stale_endpoints: list[str] = []
        payload_dict: dict[str, str] = {"body": message}
        if title:
            payload_dict["title"] = title
        payload = json.dumps(payload_dict)

        for row in rows:
            subscription_info = {
                "endpoint": row["endpoint"],
                "keys": {"p256dh": row["keys_p256dh"], "auth": row["keys_auth"]},
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=self._vapid_private_key,
                    vapid_claims={"sub": "mailto:noreply@synthia.dev"},
                )
            except WebPushException as _e:
                if _e.response is not None and _e.response.status_code in (403, 404, 410):
                    stale_endpoints.append(row["endpoint"])
                else:
                    logger.warning(f"push notification failed: {_e}")
            except Exception as _e:
                logger.warning(f"push notification failed: {_e}")

        if stale_endpoints:
            await self._pool.execute("DELETE FROM push_subscriptions WHERE endpoint = ANY($1::text[])", stale_endpoints)
            logger.info(f"removed {len(stale_endpoints)} stale push subscriptions")
