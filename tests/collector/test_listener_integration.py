# tests/collector/test_listener_integration.py
import asyncio
import json

import pytest

from apps.collector.listener import CollectorBusListener
from libs.collector.models import DeviceOnlineCommand
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_listener_ingests_valkey_events_to_internal_queue(valkey_client):
    """Интеграционный тест: Листенер слушает Редис и без потерь транслирует команды в очередь."""
    internal_queue = asyncio.Queue()

    listener = CollectorBusListener(client=valkey_client, internal_queue=internal_queue)

    # 1. Запускаем бесконечный I/O слушатель в фоне
    listener_task = asyncio.create_task(listener.listen_forever())
    await asyncio.sleep(0.02)  # Ждем оформления подписки сокета

    client = valkey_client

    # Имитируем данные Полллера в базе: сохраняем статичный JSON конфига
    dev_config = DeviceConfig(uid="switch-core", ip="10.10.10.10", check_type="icmp", collect_interval_min=15)
    await client.set("device:config:switch-core", dev_config.model_dump_json())

    # 2. Публикуем событие перехода в ONLINE в Pub/Sub канал Полллера
    payload = json.dumps({"uid": "switch-core", "status": "online"})
    await client.publish(CollectorBusListener.CONFIG_EVENT_ONLINE, payload)
    await asyncio.sleep(0.02)  # Время на чтение из сокета

    # 3. Проверяем, что листенер отработал и сбросил чистую команду в ОЗУ-очередь
    assert internal_queue.qsize() == 1
    command = await internal_queue.get()

    assert isinstance(command, DeviceOnlineCommand)
    assert command.device.uid == "switch-core"
    assert command.device.ip == "10.10.10.10"
    assert command.device.collect_interval_min == 15

    # Чистим ресурсы
    listener_task.cancel()
