# tests/test_notifier.py
from typing import AsyncGenerator

import pytest
import pytest_asyncio
import redis.asyncio as valkey

from apps.device_provider.notifier import DeviceNotificationService
from libs.events.models import DeviceConfig

CONFIG_EVENT_CREATED = DeviceNotificationService.CONFIG_EVENT_CREATED
CONFIG_EVENT_UPDATED = DeviceNotificationService.CONFIG_EVENT_UPDATED


@pytest_asyncio.fixture
async def notifier(
    valkey_client: valkey.Redis,
) -> AsyncGenerator[DeviceNotificationService, None]:
    srv = DeviceNotificationService(valkey_client)
    yield srv


@pytest.mark.asyncio
async def test_send_device_created_pubsub(notifier, valkey_dsn):
    """Проверка публикации ивента создания устройства."""
    device = DeviceConfig(uid="router-01", ip="192.168.1.1", check_type="icmp")

    client = valkey.from_url(valkey_dsn, decode_responses=True)
    async with client.pubsub() as pubsub:
        await pubsub.subscribe(CONFIG_EVENT_CREATED)

        # Отправляем извещение
        await notifier.send_device_created(device)

        # Ловим сообщение в Pub/Sub
        await pubsub.get_message(ignore_subscribe_messages=True)  # Пропуск служебного тика
        msg = await pubsub.get_message(timeout=1.0)

        assert msg is not None
        assert "router-01" in msg["data"]
        assert "device_created" in CONFIG_EVENT_CREATED
    await client.aclose()
