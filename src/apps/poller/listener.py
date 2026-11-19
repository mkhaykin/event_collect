# apps/poller/listener.py
import asyncio
import logging

import redis.asyncio as valkey
from pydantic import ValidationError

from apps.poller.models import (
    DeviceCreatedCommand,
    DeviceDeletedCommand,
    DeviceUpdatedCommand,
)
from libs.config import config
from libs.events.models import (
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    DeviceUpdatedEvent,
)
from libs.null_logger import NullLogger


class PollerBusListener:
    """
    Слушает очередь (valkey) на изменение состояния устройств,
    изменение состояния фиксирует в реестре устройств `registry`.
    """

    CONFIG_EVENT_CREATED: str = config.CONFIG_EVENT_CREATED
    CONFIG_EVENT_UPDATED: str = config.CONFIG_EVENT_UPDATED
    CONFIG_EVENT_DELETED: str = config.CONFIG_EVENT_DELETED

    def __init__(
        self,
        client: valkey.Redis,
        command_queue: asyncio.Queue,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._client = client
        self._command_queue = command_queue

    async def listen_forever(self) -> None:
        """Бесконечный цикл прослушивания шины событий Провайдера."""
        async with self._client.pubsub() as pubsub:
            channels = [self.CONFIG_EVENT_CREATED, self.CONFIG_EVENT_UPDATED, self.CONFIG_EVENT_DELETED]
            await pubsub.subscribe(*channels)
            self._logger.info("Слушаем каналы изменений конфигураций...")

            try:
                async for message in pubsub.listen():
                    if message["type"] not in ("message", "pmessage"):
                        continue

                    channel = message["channel"]
                    payload_raw = message["data"]
                    self._logger.debug(
                        "Внешнее событие в канале %s, сообщение %s",
                        channel,
                        payload_raw,
                    )

                    try:
                        msg: DeviceCreatedEvent | DeviceUpdatedEvent | DeviceDeletedEvent
                        if channel == self.CONFIG_EVENT_CREATED:
                            msg = DeviceCreatedEvent.model_validate_json(payload_raw)
                            await self._command_queue.put(DeviceCreatedCommand(device_uid=msg.uid))

                        if channel == self.CONFIG_EVENT_UPDATED:
                            msg = DeviceUpdatedEvent.model_validate_json(payload_raw)
                            await self._command_queue.put(DeviceUpdatedCommand(device_uid=msg.uid))

                        if channel == self.CONFIG_EVENT_DELETED:
                            msg = DeviceDeletedEvent.model_validate_json(payload_raw)
                            await self._command_queue.put(DeviceDeletedCommand(device_uid=msg.uid))

                    except ValidationError:
                        self._logger.exception(
                            "Ошибка валидации модели из канала %s, raw data: %s",
                            channel,
                            payload_raw,
                        )
                    except Exception:
                        self._logger.exception(
                            "Ошибка обработки Pub/Sub сообщения из канала %s",
                            channel,
                        )

            except asyncio.CancelledError:
                self._logger.info("Фоновый слушатель событий остановлен.")
            finally:
                await pubsub.unsubscribe(*channels)
