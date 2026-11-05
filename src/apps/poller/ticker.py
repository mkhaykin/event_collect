# apps/poller/ticker.py
import asyncio
import logging
import time

from apps.poller.registry import DeviceRegistry
from apps.poller.state_machine import DeviceStateMachine
from apps.poller.workers import DeviceNetworkWorker
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class PollerTickerService:
    """Основной процесс-тикер. Базовый шаг — 1 секунда."""

    def __init__(
        self,
        registry: DeviceRegistry,
        state_machine: DeviceStateMachine,
        worker_pool: DeviceNetworkWorker,
        concurrency_limit: int = 1000,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._registry = registry
        self._state_machine = state_machine
        self._worker = worker_pool
        self._semaphore = asyncio.Semaphore(concurrency_limit)

    async def start_loop(self) -> None:
        """Вечный цикл + засыпание на секунду."""
        # TODO подумать на засыпание на время.
        while True:
            current_time = time.time()
            snapshot = await self._registry.get_snapshot()

            for dev in snapshot:
                next_run = self._state_machine.get_next_run_time(dev.uid)

                if current_time >= next_run:
                    # Рассчитываем динамические параметры на основе текущего стейта
                    probes_count = self._state_machine.get_probes_config(dev.uid)

                    # Выставляем время запуска
                    # TODO не нравиться ответственность. Надо подумать.
                    self._state_machine.calculate_next_schedule(
                        uid=dev.uid,
                        current_time=current_time,
                        interval_sec=dev.check_interval_sec,
                    )

                    self._logger.debug("запускаем опрос: %s, повторов: %s", dev, probes_count)
                    asyncio.create_task(self._safe_worker_launcher(dev, probes_count))

            # TODO подумать над шагом, но пока так
            await asyncio.sleep(1.0)

    async def _safe_worker_launcher(self, dev: DeviceConfig, probes_count: int) -> None:
        """Защищает операционную систему от переполнения сокет-дескрипторов."""
        async with self._semaphore:
            await self._worker.run_probe(
                uid=dev.uid,
                ip=dev.ip,
                check_type=dev.check_type,
                port=dev.port,
                probes_count=probes_count,
            )
