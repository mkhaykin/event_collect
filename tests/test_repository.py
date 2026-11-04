# tests/test_repository.py
import pytest
import pytest_asyncio
import redis.asyncio as valkey

from apps.device_provider.repository import DeviceValkeyRepository
from libs.events.models import DeviceConfig


@pytest_asyncio.fixture
async def repository(valkey_dsn) -> DeviceValkeyRepository:
    repo = DeviceValkeyRepository(valkey_dsn)
    await repo.connect()
    yield repo
    await repo.close()


@pytest.mark.asyncio
async def test_upsert_device_created(repository, valkey_dsn):
    """Сценарий 1: Устройства нет в базе -> должно создаться."""
    device = DeviceConfig(uid="dev-1", ip="192.168.1.1", check_type="icmp")
    sync_time = "2026-11-04T12:00:00"

    result = await repository.upsert_device(device, sync_time)

    assert result.action == "created"

    # Проверяем, что ключи физически создались в Valkey с правильным TTL
    client = valkey.from_url(valkey_dsn, decode_responses=True)
    assert await client.sismember("device:all", "dev-1") == 1

    config_data = await client.get("device:config:dev-1")
    assert config_data is not None
    assert "192.168.1.1" in config_data

    assert await client.ttl("device:config:dev-1") <= 320
    await client.aclose()


@pytest.mark.asyncio
async def test_upsert_device_none_changes(repository, valkey_dsn):
    """Сценарий 2: Устройство существует и конфиг идентичен -> вердикт 'none'."""
    device = DeviceConfig(uid="dev-1", ip="192.168.1.1", check_type="icmp")
    sync_time_1 = "2026-11-04T12:00:00"
    sync_time_2 = "2026-11-04T12:30:00"

    await repository.upsert_device(device, sync_time_1)
    result = await repository.upsert_device(device, sync_time_2)

    assert result.action == "none"

    client = valkey.from_url(valkey_dsn, decode_responses=True)
    hb_data = await client.hgetall("device:heartbeat:dev-1")
    assert hb_data["updated_at"] == sync_time_2  # Время пульса обновилось
    await client.aclose()


@pytest.mark.asyncio
async def test_upsert_device_updated(repository, valkey_dsn):
    """Сценарий 3: Настройки изменились -> вердикт 'updated' с заполнением old_value."""
    old_device = DeviceConfig(uid="dev-1", ip="192.168.1.1", check_type="icmp")
    new_device = DeviceConfig(uid="dev-1", ip="192.168.1.200", check_type="port", port=80)
    sync_time = "2026-11-04T12:00:00"

    await repository.upsert_device(old_device, sync_time)
    result = await repository.upsert_device(new_device, sync_time)

    assert result.action == "updated"
    assert result.old_value.ip == "192.168.1.1"
    assert result.old_value.check_type == "icmp"
    assert result.new_value.ip == "192.168.1.200"
