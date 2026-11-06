# tests/poller/test_registry.py
import pytest

from apps.poller.registry import DeviceRegistry
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_registry_crud_operations():
    """Проверка базовых CRUD операций внутри реестра в ОЗУ."""
    registry = DeviceRegistry()
    dev = DeviceConfig(uid="router-01", ip="1.1.1.1", check_type="icmp")

    # Тест добавления
    await registry.add_or_update(dev)
    snapshot = await registry.get_snapshot()
    assert len(snapshot) == 1
    assert snapshot[0].uid == "router-01"

    # Тест обновления
    updated_dev = DeviceConfig(uid="router-01", ip="1.1.1.2", check_type="icmp")
    await registry.add_or_update(updated_dev)
    snapshot = await registry.get_snapshot()
    assert snapshot[0].ip == "1.1.1.2"

    # Тест удаления
    await registry.remove("router-01")
    snapshot = await registry.get_snapshot()
    assert len(snapshot) == 0


@pytest.mark.asyncio
async def test_registry_snapshot_isolation():
    """Крайний случай: Срез (snapshot) не должен мутировать, если после его создания изменился реестр."""
    registry = DeviceRegistry()
    dev1 = DeviceConfig(uid="dev-1", ip="1.1.1.1", check_type="icmp")
    await registry.add_or_update(dev1)

    snapshot_before = await registry.get_snapshot()

    # Добавляем второе устройство ПОСЛЕ снятия среза
    dev2 = DeviceConfig(uid="dev-2", ip="2.2.2.2", check_type="icmp")
    await registry.add_or_update(dev2)

    snapshot_after = await registry.get_snapshot()

    assert len(snapshot_before) == 1
    assert len(snapshot_after) == 2
