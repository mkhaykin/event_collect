# apps/poller/repository.py
import logging

import redis.asyncio as valkey
from pydantic import ValidationError

from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class PollerValkeyRepository:
    CONFIG_ALL_DEVICE: str = "device:all"
    CONFIG_SPECIFIC_DEVICE: str = "device:config:{uid}"

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

    async def load_all_active_configs(self) -> list[DeviceConfig]:
        """Пакетная выгрузка всего слепка конфигураций при старте."""
        if self._client is None:
            raise RuntimeError("Не выполнено подключение к ValKey")

        uids = await self._client.smembers(self.CONFIG_ALL_DEVICE)
        if not uids:
            return []

        # TODO подумать: try?
        async with self._client.pipeline(transaction=False) as pipe:
            for uid in uids:
                pipe.get(self.CONFIG_SPECIFIC_DEVICE.format(uid=uid))
            raw_jsons = await pipe.execute()

        configs = []
        for raw in raw_jsons:
            if raw:
                try:
                    configs.append(DeviceConfig.model_validate_json(raw))
                except ValidationError:
                    self._logger.exception("Ошибка загрузки модели")
                    continue
        return configs
