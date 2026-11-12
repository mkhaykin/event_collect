# tests/collector/test_collector_service.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.collector.registry import DeviceOnlineRegistry
from apps.collector.service import CollectorService
from libs.collector.models import (
    DeviceOfflineCommand,
    DeviceOnlineCommand,
    JobFinishedCommand,
)
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_service_handles_online_offline_and_finished_commands():
    """Проверка полного жизненного цикла команд в _consume_commands_loop."""
    registry = DeviceOnlineRegistry()
    mock_scheduler = MagicMock()
    mock_runner = MagicMock()
    mock_listener = MagicMock()
    mock_listener.listen_forever = AsyncMock()

    dev = DeviceConfig(uid="router-1", ip="10.0.0.1", check_type="icmp", collect_interval_min=10)
    mock_valkey_repo = MagicMock()
    mock_valkey_repo.get_device_config = AsyncMock(return_value=dev)

    mock_db_repo = MagicMock()
    mock_db_repo.log_status_change = AsyncMock()

    queue = asyncio.Queue()
    wakeup_event = asyncio.Event()

    service = CollectorService(
        registry=registry,
        scheduler=mock_scheduler,
        runner=mock_runner,
        repository=mock_valkey_repo,
        db_repo=mock_db_repo,
        listener=mock_listener,
        internal_queue=queue,
        wakeup_event=wakeup_event,
    )

    consumer_task = asyncio.create_task(service._consume_commands_loop())

    # 1. Команда ONLINE -> запрос конфига, запись в БД, добавление в реестр и регистрация в секундах (10 * 60 = 600)
    await queue.put(DeviceOnlineCommand(uid="router-1"))
    await asyncio.sleep(0.01)

    mock_valkey_repo.get_device_config.assert_called_once_with("router-1")
    mock_db_repo.log_status_change.assert_called_with("router-1", "ONLINE")
    assert "router-1" in registry
    mock_scheduler.register.assert_called_once_with("router-1", interval=600)
    assert wakeup_event.is_set()

    # 2. Команда FINISHED -> вызов mark_finished у шедулера
    wakeup_event.clear()
    await queue.put(JobFinishedCommand(uid="router-1", is_success=False))
    await asyncio.sleep(0.01)

    mock_scheduler.mark_finished.assert_called_once_with(
        "router-1",
        is_success=False,
        retry_delay_sec=CollectorService.RETRY_DELAY_SEC,
    )
    assert wakeup_event.is_set()

    # 3. Команда OFFLINE -> удаление из реестра и шедулера
    wakeup_event.clear()
    await queue.put(DeviceOfflineCommand(uid="router-1"))
    await asyncio.sleep(0.01)

    mock_db_repo.log_status_change.assert_called_with("router-1", "OFFLINE")
    assert "router-1" not in registry
    mock_scheduler.remove.assert_called_once_with("router-1")
    assert wakeup_event.is_set()

    consumer_task.cancel()


@pytest.mark.asyncio
async def test_service_sleep_loop_dispatches_and_wakes_up():
    """Проверка основного цикла запуска задач и прерываемого сна через wakeup_event."""
    registry = DeviceOnlineRegistry()
    dev = DeviceConfig(uid="switch-1", ip="10.0.0.2", check_type="icmp")
    await registry.add_or_update(dev)

    mock_scheduler = MagicMock()
    # На первом проходе возвращаем задачу, на втором проходе задач больше нет
    mock_scheduler.get_due_jobs.side_effect = [["switch-1"], []]
    mock_scheduler.seconds_until_next.return_value = None

    mock_runner = MagicMock()
    mock_listener = MagicMock()
    mock_listener.listen_forever = AsyncMock()

    queue = asyncio.Queue()
    wakeup_event = asyncio.Event()

    service = CollectorService(
        registry=registry,
        scheduler=mock_scheduler,
        runner=mock_runner,
        repository=MagicMock(),
        db_repo=MagicMock(),
        listener=mock_listener,
        internal_queue=queue,
        wakeup_event=wakeup_event,
    )

    loop_task = asyncio.create_task(service._loop())
    await asyncio.sleep(0.01)

    # Проверяем, что задача была помечена запущенной и передана в раннер
    mock_scheduler.mark_started.assert_called_once_with("switch-1")
    mock_runner.dispatch.assert_called_once_with(dev)
    assert mock_scheduler.get_due_jobs.call_count == 1

    # Будим цикл вручную через событие — должен произойти второй проход
    wakeup_event.set()
    await asyncio.sleep(0.01)

    assert mock_scheduler.get_due_jobs.call_count == 2

    loop_task.cancel()
