# apps/collector/listener.py
import asyncio
import json
import logging
from typing import Any

import redis.asyncio as valkey

from libs.collector.models import (
    DeviceOfflineCommand,
    DeviceOnlineCommand,
    DeviceUpdatedCommand,
)
from libs.config import config
from libs.null_logger import NullLogger


class CollectorBusListener:
    """Фоновый подписчик на Pub/Sub шину Poller и Device.
    Получает событие и бросает в локальную очередь."""

    CONFIG_EVENT_ONLINE: str = config.CONFIG_EVENT_ONLINE
    CONFIG_EVENT_OFFLINE: str = config.CONFIG_EVENT_OFFLINE

    CONFIG_EVENT_UPDATED: str = config.CONFIG_EVENT_UPDATED
    CONFIG_EVENT_DELETED: str = config.CONFIG_EVENT_DELETED

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
                    try:
                        data = json.loads(
                            message["data"],
                        )
                    except json.decoder.JSONDecodeError:
                        self._logger.error(
                            "Получен невалидный JSON в канале %s: %s",
                            channel,
                            str(message.get("data", ""))[:50],
                        )
                        continue

                    uid = data.get("uid")

                    if not uid:
                        # TODO: ? log ...
                        continue

                    if channel == self.CONFIG_EVENT_ONLINE:
                        self._logger.debug("Пришло событие online: %s", uid)
                        await self._queue.put(DeviceOnlineCommand(device_uid=uid))

                    elif channel == self.CONFIG_EVENT_OFFLINE:
                        self._logger.debug("Пришло событие offline: %s", uid)
                        await self._queue.put(DeviceOfflineCommand(device_uid=uid))

                    elif channel in self.CONFIG_EVENT_UPDATED:
                        self._logger.debug("Пришло событие device_updated: %s", uid)
                        await self._queue.put(DeviceUpdatedCommand(device_uid=uid))

                    elif channel == self.CONFIG_EVENT_DELETED:
                        self._logger.debug("Пришло событие device_deleted: %s", uid)
                        self._logger.debug("Поймали удаление устройства %s, сбрасываем его в offline", uid)
                        await self._queue.put(DeviceOfflineCommand(device_uid=uid))

            except asyncio.CancelledError:
                self._logger.info("слушатель шины поллера остановлен.")
            finally:
                await pubsub.unsubscribe(*channels)
