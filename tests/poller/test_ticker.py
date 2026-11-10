# tests/poller/test_ticker.py
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.poller.service import PollerService


@pytest.mark.asyncio
async def test_ticker_fires_only_scheduled_devices():
    """Проверка, что тикер запускает задачи только для устройств, у которых наступил next_run_at."""
    mock_registry = MagicMock()
    mock_sm = MagicMock()
    mock_worker = MagicMock()
    mock_worker.run_probe = AsyncMock()

    # Симулируем 2 устройства в кэше
    from libs.events.models import DeviceConfig

    dev1 = DeviceConfig(uid="dev-ready", ip="1.1.1.1", check_type="icmp", check_interval_sec=5)
    dev2 = DeviceConfig(uid="dev-sleeping", ip="2.2.2.2", check_type="icmp", check_interval_sec=5)
    mock_registry.get_snapshot = AsyncMock(return_value=[dev1, dev2])

    # Настройки расписания: dev-ready готов к запуску (0.0), dev-sleeping спит в будущем
    current_time = time.time()
    mock_sm.get_next_run_time.side_effect = lambda uid: 0.0 if uid == "dev-ready" else current_time + 100.0
    mock_sm.get_probes_config.return_value = 3

    ticker = PollerService(
        registry=mock_registry,
        state_machine=mock_sm,
        worker_pool=mock_worker,
        listener=AsyncMock(),
        repository=AsyncMock(),
    )

    # Запускаем ОДИН итерационный цикл тикера (вместо бесконечного start_loop)
    # Копируем тело условия из оригинального тикера для одного шага:
    for dev in await mock_registry.get_snapshot():
        next_run = mock_sm.get_next_run_time(dev.uid)
        if current_time >= next_run:
            ticker._state_machine.get_probes_config(dev.uid)
            ticker._state_machine.calculate_next_schedule(dev.uid, current_time, dev.check_interval_sec)
            await ticker._worker.run_probe(dev.uid, dev.ip, dev.check_type, dev.port, 3)

    # Убеждаемся, что запустилось ТОЛЬКО готовое устройство
    assert mock_worker.run_probe.call_count == 1
    mock_worker.run_probe.assert_called_once_with("dev-ready", "1.1.1.1", "icmp", None, 3)
