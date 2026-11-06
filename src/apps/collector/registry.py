# apps/collector/registry.py
import asyncio
import logging

from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class DeviceOnlineRegistry:
    """Потокобезопасный реестр конфигураций устройств, находящихся строго в статусе Online."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or NullLogger(__name__)
        self._devices: dict[str, DeviceConfig] = {}
        self._lock = asyncio.Lock()

    async def add_or_update(self, device: DeviceConfig) -> None:
        async with self._lock:
            self._devices[device.uid] = device
            self._logger.debug("Устройство %s зарегистрировано", device.uid)

    async def remove(self, uid: str) -> None:
        async with self._lock:
            if uid in self._devices:
                self._devices.pop(uid)
                self._logger.debug("Устройство %s удалено", uid)

    async def get(self, uid: str) -> DeviceConfig | None:
        async with self._lock:
            return self._devices.get(uid)

    async def get_snapshot(self) -> list[DeviceConfig]:
        async with self._lock:
            return list(self._devices.values())

    def __contains__(self, uid: str) -> bool:
        return uid in self._devices
