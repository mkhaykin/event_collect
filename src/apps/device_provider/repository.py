# apps/device_provider/repository.py
import logging
from dataclasses import dataclass
from typing import Any, Literal

import redis.asyncio as valkey
from redis.maint_notifications import MaintNotificationsConfig

from libs.events.models import (
    DeviceConfig,
)
from libs.null_logger import NullLogger


@dataclass
class Result:
    action: Literal["created", "updated", "deleted", "none"] = "none"
    new_value: DeviceConfig | None = None
    old_value: DeviceConfig | None = None


class DeviceValkeyRepository:
    CONFIG_ALL_DEVICE: str = "device:all"
    CONFIG_SPECIFIC_DEVICE: str = "device:config:{uid}"
    CONFIG_HEARTBEAT: str = "device:heartbeat:{uid}"
    CONFIG_DEVICE_TTL: int = 320

    """
    device:all — Set.
    device:config:{uid} — String (json).
    device:heartbeat:{uid} — Hash.
    """

    def __init__(
        self,
        dsn: str,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._dsn = dsn
        self._client: valkey.Redis | None = None

    async def connect(self) -> None:
        if not self._client:
            self._client = valkey.from_url(
                self._dsn,
                decode_responses=True,
                socket_timeout=None,
                socket_keepalive=True,
                maint_notifications_config=MaintNotificationsConfig(enabled=False),
            )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def upsert_device(self, device: DeviceConfig, sync_time: str) -> Result:
        """
        Атомарно обновляет стейт одного устройства в базе.
        Продлевает TTL на 320 секунд для конфига и хартбита.
        Возвращает вердикт бизнеса: 'created', 'updated' или 'none'.
        """
        # Читаем текущее состояние перед записью в рамках одного сетевого пакета
        existing_config, existing_heartbeat, in_all = await self._cur_state(device)
        stored_model = await self._data_to_model(existing_config)
        is_mutated = stored_model is not None and stored_model != device

        created_at = existing_heartbeat.get("created_at", sync_time)

        if not stored_model:
            await self._update(device, created_at, sync_time)
            return Result("created", new_value=device)

        if not is_mutated:
            await self._update_heartbeat(device, sync_time)
            return Result("none", new_value=device, old_value=stored_model)

        await self._update(device, created_at, sync_time)
        return Result("updated", new_value=device, old_value=stored_model)

    async def _update_heartbeat(
        self,
        device: DeviceConfig,
        updated_at: str,
    ) -> None:
        if self._client is None:
            raise RuntimeError("Не подготовлен клиент")

        heartbeat_key = self.CONFIG_HEARTBEAT.format(uid=device.uid)

        async with self._client.pipeline(transaction=True) as pipe:
            pipe.hset(heartbeat_key, mapping={"updated_at": updated_at})
            pipe.expire(heartbeat_key, self.CONFIG_DEVICE_TTL)

            await pipe.execute()

    async def _update(
        self,
        device: DeviceConfig,
        created_at: str,
        updated_at: str,
    ) -> None:
        if self._client is None:
            raise RuntimeError("Не подготовлен клиент")

        config_key = self.CONFIG_SPECIFIC_DEVICE.format(uid=device.uid)
        heartbeat_key = self.CONFIG_HEARTBEAT.format(uid=device.uid)

        async with self._client.pipeline(transaction=True) as pipe:
            pipe.sadd(self.CONFIG_ALL_DEVICE, device.uid)
            pipe.set(config_key, device.model_dump_json(), ex=self.CONFIG_DEVICE_TTL)
            pipe.hset(heartbeat_key, mapping={"created_at": created_at, "updated_at": updated_at})
            pipe.expire(heartbeat_key, self.CONFIG_DEVICE_TTL)

            await pipe.execute()

    async def _data_to_model(self, data: str | None) -> DeviceConfig | None:
        if data:
            try:
                return DeviceConfig.model_validate_json(data)
            except Exception as e:
                self._logger.error(e)

        return None

    async def _cur_state(
        self,
        dev: DeviceConfig,
    ) -> tuple[Any, Any, Any]:
        if self._client is None:
            raise RuntimeError("Не подготовлен клиент")

        config_key = self.CONFIG_SPECIFIC_DEVICE.format(uid=dev.uid)
        heartbeat_key = self.CONFIG_HEARTBEAT.format(uid=dev.uid)

        async with self._client.pipeline(transaction=False) as pipe:
            pipe.sismember(self.CONFIG_ALL_DEVICE, dev.uid)
            pipe.hgetall(heartbeat_key)
            pipe.get(config_key)
            in_all, existing_heartbeat, existing_config, *_ = await pipe.execute()

        return existing_config, existing_heartbeat, in_all
