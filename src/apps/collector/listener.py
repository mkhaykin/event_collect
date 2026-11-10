# apps/collector/listener.py
import asyncio
import json
import logging
from typing import Any

import redis.asyncio as valkey

from libs.collector.models import DeviceOfflineCommand, DeviceOnlineCommand
from libs.config import config
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class CollectorBusListener:
    """Фоновый подписчик на Pub/Sub шину Poller."""

    CONFIG_EVENT_ONLINE: str = config.CONFIG_EVENT_ONLINE
    CONFIG_EVENT_OFFLINE: str = config.CONFIG_EVENT_OFFLINE
    CONFIG_SPECIFIC_DEVICE: str = config.CONFIG_SPECIFIC_DEVICE

    def __init__(
        self,
        client: valkey.Redis,
        internal_queue: asyncio.Queue[Any],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._queue = internal_queue
        self._client = client

    async def listen_forever(self) -> None:
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
