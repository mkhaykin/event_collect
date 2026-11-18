# apps/collector/actions/interface.py
from typing import Protocol

from libs.collector.models import CollectResult
from libs.models.config import DeviceConfig


# TODO подумать и может отказаться, есть базовый Action (там с конструктором!)
class CollectAction(Protocol):
    """для плагинов сбора данных (SNMP, SSH, REST API, etc.)."""

    async def execute(self, device: DeviceConfig) -> CollectResult: ...
