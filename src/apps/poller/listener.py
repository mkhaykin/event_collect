# apps/poller/listener.py
import asyncio
import json
import logging

import redis.asyncio as valkey

from apps.poller.registry import DeviceRegistry
from libs.events.models import (
    DeviceConfig,
)
from libs.null_logger import NullLogger


class PollerBusListener:
    CONFIG_EVENT_CREATED: str = "events:device_created"
    CONFIG_EVENT_UPDATED: str = "events:device_updated"
    CONFIG_EVENT_DELETED: str = "events:device_deleted"

    def __init__(
        self,
        valkey_url: str,
        registry: DeviceRegistry,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._url = valkey_url
        self._registry = registry
        self._client: valkey.Redis | None = None

    async def connect(self) -> None:
        if not self._client:
            self._client = valkey.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def listen_forever(self) -> None:
        """Бесконечный цикл прослушивания шины событий Провайдера."""
        if not self._client:
            raise RuntimeError("Слушатель не подключен к ValKey")

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

                    try:
                        data = json.loads(payload_raw)

                        if channel in (self.CONFIG_EVENT_CREATED, self.CONFIG_EVENT_UPDATED):
                            # Извлекаем модель устройства из тела эвента
                            device_data = data.get("device")
                            if device_data:
                                dev = DeviceConfig.model_validate(device_data)
                                await self._registry.add_or_update(dev)
                                self._logger.info(
                                    "Устройство %s добавлено/обновлено в реестре.",
                                    dev.uid,
                                )

                        elif channel == self.CONFIG_EVENT_DELETED:
                            uid = data.get("uid")
                            if uid:
                                await self._registry.remove(uid)
                                self._logger.info(
                                    "Устройство %s удалено из реестра.",
                                    uid,
                                )
                        else:
                            pass  # TODO пишем в лог

                    except Exception:  # TODO исправить на конкретные. Ну и разделить
                        self._logger.exception(
                            "Ошибка обработки Pub/Sub сообщения из канала %s",
                            channel,
                        )

            except asyncio.CancelledError:
                self._logger.info("Фоновый слушатель событий остановлен.")
            finally:
                await pubsub.unsubscribe(*channels)
