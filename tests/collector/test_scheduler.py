# tests/collector/test_scheduler.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.collector.registry import DeviceOnlineRegistry
from apps.collector.scheduler import JobScheduler
from libs.collector.models import CollectResult
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
@patch("time.time", return_value=1700000000.0)
async def test_scheduler_optimistic_shift(mock_time):
    """Проверка, что планировщик оптимистично переносит время запуска вперед ДО старта задачи."""
    wakeup_event = asyncio.Event()
    registry = DeviceOnlineRegistry()

    mock_action = MagicMock()
    mock_action.execute = AsyncMock(
        return_value=CollectResult(uid="dev-1", is_success=True, execution_time_sec=0.1)
    )

    scheduler = JobScheduler(action=mock_action, registry=registry, wakeup_event=wakeup_event)
    dev = DeviceConfig(uid="dev-1", ip="1.1.1.1", check_type="icmp", collect_interval_min=5)

    await scheduler.add_device(dev)

    # Запускаем триггер. Время следующего запуска должно прыгнуть на 5 минут вперед (300 секунд)
    wait_time = await scheduler.trigger_and_schedule_next()

    assert scheduler._schedule["dev-1"] == 1700000000.0 + 300.0
    assert wait_time == 300.0

    # Даем фоновой таске отработать
    await asyncio.sleep(0.01)
    mock_action.execute.assert_called_once_with(dev)


@pytest.mark.asyncio
async def test_scheduler_reactive_retry_on_failure():
    """Проверка, что при сбое сбора расписание реактивно сокращается до 60 секунд."""
    wakeup_event = asyncio.Event()
    registry = DeviceOnlineRegistry()

    mock_action = MagicMock()
    # Имитируем сбой сбора данных
    mock_action.execute = AsyncMock(return_value=CollectResult(uid="dev-fail", is_success=False))

    scheduler = JobScheduler(action=mock_action, registry=registry, wakeup_event=wakeup_event)
    dev = DeviceConfig(uid="dev-fail", ip="1.1.1.1", check_type="icmp", collect_interval_min=30)

    # Жестко фиксируем время старта через patch контекста
    with patch("time.time", return_value=1000.0):
        await scheduler.add_device(dev)
        await scheduler.trigger_and_schedule_next()

    # Воркер упал в фоне. Ждем выполнения `_safe_execute_launcher`
    with patch("time.time", return_value=1001.0):
        await asyncio.sleep(0.02)

        # Расписание должно скорректироваться на 1001.0 (время падения) + 60 секунд
        assert scheduler._schedule["dev-fail"] == 1061.0
        assert wakeup_event.is_set()  # Движок разбужен для пересчета сна


@pytest.mark.asyncio
async def test_scheduler_ghost_device_protection():
    """Крайний случай: Если устройство удалили через remove_device во время опроса,
    воркер после падения не должен вернуть его в расписание."""
    wakeup_event = asyncio.Event()
    registry = DeviceOnlineRegistry()

    mock_action = MagicMock()
    # Имитируем, что сбор данных провалился
    mock_action.execute = AsyncMock(return_value=CollectResult(uid="ghost", is_success=False))

    scheduler = JobScheduler(action=mock_action, registry=registry, wakeup_event=wakeup_event)
    dev = DeviceConfig(uid="ghost", ip="1.1.1.1", check_type="icmp", collect_interval_min=5)

    # 1. Добавляем устройство и ставим в расписание
    await scheduler.add_device(dev)
    await scheduler.trigger_and_schedule_next()

    # 2. ИСПРАВЛЕНИЕ: Имитируем реальное поведение Движка —
    # удаляем устройство через Шедулер, пока воркер крутится в фоне!
    # Это сотрет девайс и из реестра, и из карты self._schedule
    await scheduler.remove_device("ghost")

    # 3. Даем фоновому воркеру завершиться
    await asyncio.sleep(0.02)

    # ПРОВЕРКА: Проверка 'if device.uid in self._schedule' должна была защитить нас,
    # и устройство не должно было воскреснуть в расписании
    assert "ghost" not in scheduler._schedule
