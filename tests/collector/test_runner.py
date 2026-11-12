# tests/collector/test_runner.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.collector.runner import JobRunner
from libs.collector.models import CollectResult, JobFinishedCommand
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_runner_dispatches_and_reports_success():
    """Проверка успешного выполнения плагина и отправки JobFinishedCommand в очередь."""
    queue = asyncio.Queue()
    mock_action = MagicMock()
    expected_result = CollectResult(
        uid="dev-1", is_success=True, execution_time_sec=0.2, payload=None, error_message=None
    )
    runner = JobRunner(action=mock_action, internal_queue=queue)
    mock_action.execute = AsyncMock(return_value=expected_result)

    runner = JobRunner(action=mock_action, internal_queue=queue, concurrency_limit=5)
    device = DeviceConfig(uid="dev-1", ip="1.1.1.1", check_type="icmp")

    runner.dispatch(device)

    # Ждем завершения фоновой задачи
    cmd = await asyncio.wait_for(queue.get(), timeout=1.0)

    assert isinstance(cmd, JobFinishedCommand)
    assert cmd.uid == "dev-1"
    assert cmd.is_success is True
    assert cmd.result == expected_result
    mock_action.execute.assert_called_once_with(device)


@pytest.mark.asyncio
async def test_runner_handles_action_crash_gracefully():
    """Крайний случай: Если плагин упал с исключением, раннер обязан отправить is_success=False."""
    queue = asyncio.Queue()
    mock_action = MagicMock()
    mock_action.execute = AsyncMock(side_effect=RuntimeError("SNMP Timeout crash"))

    runner = JobRunner(action=mock_action, internal_queue=queue)
    device = DeviceConfig(uid="dev-crash", ip="1.1.1.1", check_type="icmp")

    runner.dispatch(device)

    cmd = await asyncio.wait_for(queue.get(), timeout=1.0)

    assert isinstance(cmd, JobFinishedCommand)
    assert cmd.uid == "dev-crash"
    assert cmd.is_success is False
    assert cmd.result is None
