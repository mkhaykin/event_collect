# apps/collector/listener.py
import asyncio
import json
import logging
from typing import Any

import redis.asyncio as valkey
from redis.maint_notifications import MaintNotificationsConfig

from libs.collector.models import DeviceOfflineCommand, DeviceOnlineCommand
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class CollectorBusListener:
    """Фоновый подписчик на Pub/Sub шину Poller."""

    CONFIG_EVENT_ONLINE: str = "events:device_online"
    CONFIG_EVENT_OFFLINE: str = "events:device_offline"
    CONFIG_SPECIFIC_DEVICE: str = "device:config:{uid}"

    def __init__(
        self,
        valkey_url: str,
        internal_queue: asyncio.Queue[Any],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._url = valkey_url
        self._queue = internal_queue
        self._client: valkey.Redis | None = None

    async def connect(self) -> None:
        if not self._client:
            self._client = valkey.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=None,
                socket_keepalive=True,
                maint_notifications_config=MaintNotificationsConfig(enabled=False),
            )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def listen_forever(self) -> None:
        if not self._client:
            raise RuntimeError("CollectorBusListener не подключен к Valkey.")

        async with self._client.pubsub() as pubsub:
            channels = [self.CONFIG_EVENT_ONLINE, self.CONFIG_EVENT_OFFLINE]
            await pubsub.subscribe(*channels)
            self._logger.info("слушатель шины поллера запущен.")

            try:
                async for message in pubsub.listen():
                    if message["type"] not in ("message", "pmessage"):
                        continue

                    channel = message["channel"]
                    data = json.loads(message["data"])
                    uid = data.get("uid")

                    if not uid:
                        continue

                    if channel == self.CONFIG_EVENT_ONLINE:
                        raw_config = await self._client.get(self.CONFIG_SPECIFIC_DEVICE.format(uid=uid))
                        if raw_config:
                            dev = DeviceConfig.model_validate_json(raw_config)
                            await self._queue.put(DeviceOnlineCommand(device=dev))

                    elif channel == self.CONFIG_EVENT_OFFLINE:
                        await self._queue.put(DeviceOfflineCommand(uid=uid))

            except asyncio.CancelledError:
                self._logger.info("слушатель шины поллера остановлен.")
            finally:
                await pubsub.unsubscribe(*channels)
