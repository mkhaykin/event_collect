# tests/collector/test_engine.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.collector.service import CollectorService, SomeClass
from libs.collector.models import DeviceOnlineCommand
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_engine_consumes_queue_and_wakes_up():
    """Проверка, что движок ядра вычитывает очередь и перезапускает цикл планирования."""
    mock_scheduler = MagicMock()
    # Возвращаем None, чтобы цикл засыпал на wakeup_event.wait()
    mock_scheduler.trigger_and_schedule_next = AsyncMock(return_value=None)
    mock_scheduler.add_device = AsyncMock()

    mock_db = MagicMock()
    mock_db.log_status_change = AsyncMock()

    internal_queue = asyncio.Queue()
    wakeup_event = asyncio.Event()

    engine = CollectorService(
        scheduler=mock_scheduler,
        internal_queue=internal_queue,
        wakeup_event=wakeup_event,
        db_repo=mock_db,
        listener=AsyncMock(),
        queue_processor=SomeClass(
            scheduler=mock_scheduler,
            internal_queue=internal_queue,
            wakeup_event=wakeup_event,
            db_repo=mock_db,
        ),
    )

    # 1. Запускаем оркестратор. Он выполнит 1-й проход trigger_and_schedule_next и уснет
    engine_task = asyncio.create_task(engine.start_loop())
    await asyncio.sleep(0.01)  # Даем ему уйти в await wakeup_event.wait()

    assert mock_scheduler.trigger_and_schedule_next.call_count == 1

    # 2. Имитируем прилет команды из очереди
    dev = DeviceConfig(uid="router-new", ip="9.9.9.9", check_type="icmp")
    await internal_queue.put(DeviceOnlineCommand(device=dev))

    # Даем время воркеру обработать команду, сделать .set(),
    # разбудить цикл, сделать 2-й проход и снова очистить эвент
    await asyncio.sleep(0.02)

    # 3. ПРОВЕРКА: Движок обязан был проснуться и вызвать триггер ВТОРОЙ раз!
    assert mock_scheduler.trigger_and_schedule_next.call_count == 2

    # Бизнес-эффект тоже должен быть достигнут
    mock_scheduler.add_device.assert_called_once_with(dev)
    mock_db.log_status_change.assert_called_once_with("router-new", "ONLINE")

    # Чистим таски
    engine_task.cancel()
