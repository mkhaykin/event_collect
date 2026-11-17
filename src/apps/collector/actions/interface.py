# apps/collector/actions/interface.py
from typing import Protocol

from libs.collector.models import CollectResult
from libs.events.models import DeviceConfig


class CollectAction(Protocol):
    """для плагинов сбора данных (SNMP, SSH, REST API, etc.)."""

    async def execute(self, device: DeviceConfig) -> CollectResult: ...
