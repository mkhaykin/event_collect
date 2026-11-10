# apps/poller/service.py
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Self

from redis.asyncio import from_url
from redis.maint_notifications import MaintNotificationsConfig

from apps.poller.bus_notifier import StatusBusNotifier
from apps.poller.checkers import IcmpChecker
from apps.poller.listener import PollerBusListener
from apps.poller.registry import DeviceRegistry
from apps.poller.repository import PollerValkeyRepository
from apps.poller.state_machine import DeviceStateMachine
from apps.poller.workers import DeviceNetworkWorker
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger
from libs.poller.models import DeviceProbeResult


class PollerService:
    """Основной процесс-тикер. Базовый шаг — 1 секунда."""

    def __init__(  # noqa: PLR0913
        self,
        registry: DeviceRegistry,
        state_machine: DeviceStateMachine,
        worker_pool: DeviceNetworkWorker,
        listener: PollerBusListener,
        repository: PollerValkeyRepository,
        *,
        concurrency_limit: int = 1000,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._registry = registry
        self._state_machine = state_machine
        self._worker = worker_pool
        self._listener = listener
        self._repository = repository

        self._semaphore = asyncio.Semaphore(concurrency_limit)

    async def start_loop(self) -> None:
        """Вечный цикл + засыпание на секунду."""
        # запускаем хранение состояний
        sm_task = asyncio.create_task(self._state_machine.start_processing())
        # тут поток слушателя от device provider-а
        listener_task = asyncio.create_task(self._listener.listen_forever())

        self._logger.info("Стартовая загрузка устройств из ValKey...")
        initial_devices = await self._repository.load_all_active_configs()
        for dev in initial_devices:
            await self._registry.add_or_update(dev)
        self._logger.info("найдено устройств: %s", len(initial_devices))

        try:
            await self._loop()
        finally:
            sm_task.cancel()
            listener_task.cancel()

    async def _loop(self) -> None:
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
                    # TODO не нравится ответственность. Надо подумать.
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

    @classmethod
    @asynccontextmanager
    async def factory(
        cls,
        valkey_dsn: str,
        *,
        concurrency_limit: int = 1000,
        logger: logging.Logger | None = None,
    ) -> AsyncGenerator[Self, None]:
        client = await from_url(
            valkey_dsn,
            decode_responses=True,
            socket_timeout=None,
            socket_keepalive=True,
            maint_notifications_config=MaintNotificationsConfig(enabled=False),
        )

        repository = PollerValkeyRepository(
            client,
            logger=logger,
        )

        queue: asyncio.Queue[DeviceProbeResult] = asyncio.Queue()

        bus_notifier = StatusBusNotifier(
            client,
            logger=logger,
        )
        state_machine = DeviceStateMachine(
            bus_notifier,
            queue,
            logger=logger,
        )

        # icmp "проверялка"
        # TODO ее не надо так передавать, она зависит от конфига, но пока так
        checker = IcmpChecker(logger=logger)
        worker_pool = DeviceNetworkWorker(
            checker,
            queue,
            logger=logger,
        )

        registry = DeviceRegistry()
        bus_listener = PollerBusListener(
            client,
            registry,
        )
        instance = cls(
            registry,
            state_machine,
            worker_pool,
            bus_listener,
            repository,
            concurrency_limit=concurrency_limit,
            logger=logger,
        )

        try:
            yield instance
        finally:
            await client.aclose()
