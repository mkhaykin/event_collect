# tests/poller/test_poller_integration.py
import asyncio
import json

import pytest

from apps.poller.bus_notifier import StatusBusNotifier
from apps.poller.listener import PollerBusListener
from apps.poller.registry import DeviceRegistry
from apps.poller.repository import PollerValkeyRepository
from libs.events.models import DeviceConfig

CONFIG_EVENT_CREATED: str = "events:device_created"
CONFIG_EVENT_UPDATED: str = "events:device_updated"
CONFIG_EVENT_DELETED: str = "events:device_deleted"

CONFIG_EVENT_ONLINE: str = "events:device_online"
CONFIG_EVENT_OFFLINE: str = "events:device_offline"


@pytest.mark.asyncio
async def test_repository_load_start_configs(valkey_client):
    """Интеграционный тест: Проверка пакетной выгрузки конфигураций репозиторием Полллера."""
    client = valkey_client

    # Имитируем работу Device Provider: пишем индексы и JSON-строку
    dev = DeviceConfig(uid="router-x", ip="10.0.0.1", check_type="icmp")
    await client.sadd("device:all", "router-x")
    await client.set("device:config:router-x", dev.model_dump_json())

    repo = PollerValkeyRepository(valkey_client)

    configs = await repo.load_all_active_configs()
    assert len(configs) == 1
    assert configs[0].uid == "router-x"
    assert configs[0].ip == "10.0.0.1"


@pytest.mark.asyncio
async def test_bus_notifier_sends_events_to_valkey(valkey_client):
    """Интеграционный тест: Проверка, что StatusBusNotifier физически публикует сообщения в Valkey."""
    notifier = StatusBusNotifier(valkey_client)

    client = valkey_client
    async with client.pubsub() as pubsub:
        await pubsub.subscribe(StatusBusNotifier.CONFIG_EVENT_ONLINE)

        await notifier.notify_online("dev-online-1")

        await pubsub.get_message(ignore_subscribe_messages=True)
        msg = await pubsub.get_message(timeout=1.0)
        assert msg is not None
        data = json.loads(msg["data"])
        assert data["uid"] == "dev-online-1"
        assert data["status"] == "online"


@pytest.mark.asyncio
async def test_bus_listener_runtime_updates(valkey_client):
    """Интеграционный тест: Фоновый слушатель должен на лету менять DeviceRegistry при получении ивентов."""
    registry = DeviceRegistry()
    listener = PollerBusListener(valkey_client, registry)

    # Запускаем слушатель в фоне
    listener_task = asyncio.create_task(listener.listen_forever())
    await asyncio.sleep(0.1)  # Даем время на подписку

    client = valkey_client

    # 1. Тестируем накат события создания устройства
    dev = DeviceConfig(uid="runtime-dev", ip="5.5.5.5", check_type="icmp")
    event_payload = json.dumps({"device": dev.model_dump()})
    await client.publish(CONFIG_EVENT_CREATED, event_payload)
    await asyncio.sleep(0.1)  # Ожидаем обработку эвента корутиной

    snapshot = await registry.get_snapshot()
    assert len(snapshot) == 1
    assert snapshot[0].uid == "runtime-dev"

    # 2. Тестируем накат события удаления устройства
    delete_payload = json.dumps({"uid": "runtime-dev"})
    await client.publish(CONFIG_EVENT_DELETED, delete_payload)
    await asyncio.sleep(0.1)

    snapshot = await registry.get_snapshot()
    assert len(snapshot) == 0

    listener_task.cancel()
