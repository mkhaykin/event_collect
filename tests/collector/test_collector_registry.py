# tests/collector/test_collector_registry.py
import pytest

from apps.collector.registry import DeviceOnlineRegistry
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_registry_crud_and_contains():
    """Проверка базовых CRUD операций и работы оператора `in`."""
    registry = DeviceOnlineRegistry()
    dev = DeviceConfig(uid="switch-01", ip="10.0.0.1", check_type="icmp")

    # Тест добавления
    await registry.add_or_update(dev)
    assert dev.uid in registry  # Проверка __contains__
    assert await registry.get("switch-01") == dev

    # Тест удаления
    await registry.remove("switch-01")
    assert "switch-01" not in registry
    assert await registry.get("switch-01") is None


@pytest.mark.asyncio
async def test_registry_snapshot_isolation():
    """Крайний случай: snapshot не должен меняться после его генерации."""
    registry = DeviceOnlineRegistry()
    dev1 = DeviceConfig(uid="dev-1", ip="1.1.1.1", check_type="icmp")
    await registry.add_or_update(dev1)

    snapshot_1 = await registry.get_snapshot()

    # Добавляем устройство после снятия снимка
    dev2 = DeviceConfig(uid="dev-2", ip="2.2.2.2", check_type="icmp")
    await registry.add_or_update(dev2)

    snapshot_2 = await registry.get_snapshot()

    assert len(snapshot_1) == 1
    assert len(snapshot_2) == 2
