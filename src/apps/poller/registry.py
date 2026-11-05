# apps/poller/registry.py
import asyncio

from libs.events.models import DeviceConfig


class DeviceRegistry:
    """Потокобезопасный реестр конфигураций устройств. По сути обертка над словарем."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceConfig] = {}
        self._lock = asyncio.Lock()

    async def add_or_update(self, device: DeviceConfig) -> None:
        async with self._lock:
            self._devices[device.uid] = device

    async def remove(self, uid: str) -> None:
        async with self._lock:
            self._devices.pop(uid, None)

    async def get_snapshot(self) -> tuple[DeviceConfig, ...]:
        """Возвращает изолированную копию списка для итератора Ticker."""
        async with self._lock:
            return tuple(self._devices.values())
