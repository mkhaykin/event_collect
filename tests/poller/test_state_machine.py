# tests/poller/test_state_machine.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.poller.state_machine import DeviceStateMachine
from libs.poller.models import DeviceProbeResult


@pytest.mark.asyncio
async def test_state_machine_streaks_and_transitions():
    """Проверка логики смены статусов при накоплении стрейков (3 успеха / 3 неудачи)."""
    mock_notifier = MagicMock()
    mock_notifier.notify_online = AsyncMock()
    mock_notifier.notify_offline = AsyncMock()
    queue = asyncio.Queue()

    sm = DeviceStateMachine(notifier=mock_notifier, result_queue=queue)

    # 1. Симулируем 3 последовательных успешных пробы -> переход в online
    for _ in range(3):
        await sm._process_single_result(DeviceProbeResult(uid="dev-1", is_success=True))

    assert sm._states["dev-1"].current_status == "online"
    mock_notifier.notify_online.assert_called_once_with("dev-1")

    # 2. Симулируем 3 последовательных сбоя -> переход в offline
    for _ in range(3):
        await sm._process_single_result(DeviceProbeResult(uid="dev-1", is_success=False))

    assert sm._states["dev-1"].current_status == "offline"
    mock_notifier.notify_offline.assert_called_once_with("dev-1")


@pytest.mark.asyncio
async def test_state_machine_dynamic_scheduling_and_probes():
    """Проверка изменения интервалов опроса (взаимно простые сетки) и объема проб на основе статуса."""
    mock_notifier = MagicMock()
    mock_notifier.notify_online = AsyncMock()
    mock_notifier.notify_offline = AsyncMock()
    sm = DeviceStateMachine(notifier=mock_notifier, result_queue=asyncio.Queue())

    # По умолчанию (для unknown/offline)
    assert sm.get_probes_config("dev-1") == 1  # 1 проба для офлайна
    sm.calculate_next_schedule(uid="dev-1", current_time=100.0, interval_sec=5)
    assert sm.get_next_run_time("dev-1") == 110.0  # Интервал умножен на 2 (10 сек)

    # Переводим девайс в online
    for _ in range(3):
        await sm._process_single_result(DeviceProbeResult(uid="dev-1", is_success=True))

    # Для online статуса
    assert sm.get_probes_config("dev-1") == 3  # 3 пробы для онлайна
    sm.calculate_next_schedule(uid="dev-1", current_time=100.0, interval_sec=7)  # интервал 7 секунд
    assert sm.get_next_run_time("dev-1") == 107.0  # Чистые 7 секунд без сдвигов
