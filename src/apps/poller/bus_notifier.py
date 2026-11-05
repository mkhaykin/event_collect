# apps/poller/bus_notifier.py
import json
import logging

import redis.asyncio as valkey

from libs.null_logger import NullLogger


class StatusBusNotifier:
    CONFIG_EVENT_ONLINE: str = "events:device_online"
    CONFIG_EVENT_OFFLINE: str = "events:device_offline"

    def __init__(
        self,
        valkey_url: str,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._url = valkey_url
        self._client: valkey.Redis | None = None

    async def connect(self) -> None:
        if not self._client:
            self._client = valkey.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def notify_online(self, uid: str) -> None:
        if not self._client:
            raise RuntimeError("Notifier не подключен к ValKey")

        payload = json.dumps({"uid": uid, "status": "online"})
        await self._client.publish(self.CONFIG_EVENT_ONLINE, payload)
        self._logger.info(f"устройство {uid} выведено в ONLINE")

    async def notify_offline(self, uid: str) -> None:
        if not self._client:
            raise RuntimeError("Notifier не подключен к ValKey")

        payload = json.dumps({"uid": uid, "status": "offline"})
        await self._client.publish(self.CONFIG_EVENT_OFFLINE, payload)
        self._logger.info(f"устройство {uid} отправлено в OFFLINE")
