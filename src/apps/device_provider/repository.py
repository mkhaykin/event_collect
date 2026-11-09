# apps/device_provider/repository.py
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal

import redis.asyncio as valkey
from redis.asyncio import from_url
from redis.maint_notifications import MaintNotificationsConfig

from libs.config import config
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
    CONFIG_ALL_DEVICE: str = config.CONFIG_ALL_DEVICE
    CONFIG_SPECIFIC_DEVICE: str = config.CONFIG_SPECIFIC_DEVICE
    CONFIG_HEARTBEAT: str = config.CONFIG_HEARTBEAT
    CONFIG_DEVICE_TTL: int = config.CONFIG_DEVICE_TTL

    def __init__(
        self,
        client: valkey.Redis,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._client: valkey.Redis = client
        self._logger = logger or NullLogger(__name__)

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
        config_key = self.CONFIG_SPECIFIC_DEVICE.format(uid=dev.uid)
        heartbeat_key = self.CONFIG_HEARTBEAT.format(uid=dev.uid)

        async with self._client.pipeline(transaction=False) as pipe:
            pipe.sismember(self.CONFIG_ALL_DEVICE, dev.uid)
            pipe.hgetall(heartbeat_key)
            pipe.get(config_key)
            in_all, existing_heartbeat, existing_config, *_ = await pipe.execute()

        return existing_config, existing_heartbeat, in_all

    async def clear_deleted_devices(self) -> list[str]:
        """
        Возращает список удаленных uid. Сравниваем все что есть в "device:all"
        и что осталось "device:config:{uid}".
        """
        config_keys = self.CONFIG_SPECIFIC_DEVICE.format(uid="*")

        # собираем живые конфиги, так как тут они протухают, те, что не продлевались уже исключены
        keys: AsyncGenerator = (key async for key in self._client.scan_iter(match=config_keys))
        uids = {key.split(":")[-1] async for key in keys}
        deleted = [
            uid
            # проходим по множеству все устройств, тут они не протухают
            async for uid in self._client.sscan_iter(self.CONFIG_ALL_DEVICE)
            if uid not in uids
        ]
        async with self._client.pipeline(transaction=False) as pipe:
            for uid in deleted:
                pipe.delete(self.CONFIG_SPECIFIC_DEVICE.format(uid=uid))
            await pipe.execute()
        return deleted


async def main() -> None:
    client = await from_url(
        config.VALKEY_DSN,
        decode_responses=True,
        socket_timeout=None,
        socket_keepalive=True,
        maint_notifications_config=MaintNotificationsConfig(enabled=False),
    )

    try:
        rep = DeviceValkeyRepository(client=client)
        print(await rep.clear_deleted_devices())
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
