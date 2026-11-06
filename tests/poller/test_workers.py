# tests/poller/test_workers.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.poller.workers import DeviceNetworkWorker


@pytest.mark.asyncio
async def test_worker_success_flow():
    """Проверка успешного выполнения сетевой пробы воркером."""
    queue = asyncio.Queue()
    mock_checker = MagicMock()
    # Симулируем успешный ответ плагина: (is_ok, latency, loss)
    mock_checker.probe = AsyncMock(return_value=(True, 15.5, 0.0))

    worker = DeviceNetworkWorker(checker=mock_checker, result_queue=queue)
    await worker.run_probe(uid="dev-1", ip="1.1.1.1", check_type="icmp", port=None, probes_count=3)

    assert queue.qsize() == 1
    result = await queue.get()
    assert result.is_success is True
    assert result.latency_ms == 15.5
    assert result.packet_loss == 0.0


@pytest.mark.asyncio
async def test_worker_timeout_handling():
    """Крайний случай: Плагин завис. Воркер должен прервать его по TimeoutError и зафиксировать fail."""
    queue = asyncio.Queue()
    mock_checker = MagicMock()

    # Заставляем плагин спать 10 секунд (дольше лимита воркера в 4.0с)
    async def slow_probe(*args, **kwargs):
        await asyncio.sleep(10.0)
        return True, 0.0, 0.0

    mock_checker.probe = slow_probe

    worker = DeviceNetworkWorker(checker=mock_checker, result_queue=queue)
    await worker.run_probe(uid="dev-1", ip="1.1.1.1", check_type="icmp", port=None, probes_count=3)

    result = await queue.get()
    assert result.is_success is False
    assert result.packet_loss == 100.0
    assert "TimeoutError" in result.error_message


@pytest.mark.asyncio
async def test_worker_network_exception_handling():
    """Крайний случай: Сетевая карта выбросила системную ошибку. Воркер обязан перехватить её."""
    queue = asyncio.Queue()
    mock_checker = MagicMock()
    mock_checker.probe = AsyncMock(side_effect=ConnectionRefusedError("Host down"))

    worker = DeviceNetworkWorker(checker=mock_checker, result_queue=queue)
    await worker.run_probe(uid="dev-1", ip="1.1.1.1", check_type="icmp", port=None, probes_count=1)

    result = await queue.get()
    assert result.is_success is False
    assert result.packet_loss == 100.0
    assert "NetworkError" in result.error_message
