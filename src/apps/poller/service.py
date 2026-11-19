# apps/poller/service.py
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Self

from redis.asyncio import from_url
from redis.maint_notifications import MaintNotificationsConfig

from apps.device_provider.repository import DeviceConfigRepository
from apps.poller.bus_notifier import StatusBusNotifier
from apps.poller.ch_buffer import ClickHouseMetricsBuffer
from apps.poller.checkers import IcmpChecker
from apps.poller.listener import PollerBusListener
from apps.poller.models import (
    DeviceCreatedCommand,
    DeviceDeletedCommand,
    DeviceUpdatedCommand,
)
from apps.poller.registry import DeviceRegistry
from apps.poller.state_machine import DeviceStateMachine
from apps.poller.workers import DeviceNetworkWorker
from libs.models.config import DeviceConfig
from libs.null_logger import NullLogger
from libs.poller.models import DeviceProbeResult
from libs.service_tracker import ServiceLifecycleTracker
from libs.store import Store, get_client


class PollerService:
    """Основной процесс."""

    def __init__(  # noqa: PLR0913 PLR0917
        self,
        registry: DeviceRegistry,
        state_machine: DeviceStateMachine,
        worker_pool: DeviceNetworkWorker,
        listener: PollerBusListener,
        repository: DeviceConfigRepository,
        command_queue: asyncio.Queue,
        metrics_buffer: ClickHouseMetricsBuffer | None = None,
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

        self._metrics_buffer = metrics_buffer

        self._command_queue = command_queue

        self._semaphore = asyncio.Semaphore(concurrency_limit)

    async def start_loop(self) -> None:
        """Вечный цикл + засыпание на секунду."""
        # запускаем хранение состояний
        sm_task = asyncio.create_task(self._state_machine.start_processing())
        # тут поток слушателя от device provider-а
        listener_task = asyncio.create_task(self._listener.listen_forever())
        # управляющий цикл
        command_loop = asyncio.create_task(self._consume_commands_loop())

        if self._metrics_buffer:
            metrics_task = asyncio.create_task(self._metrics_buffer.start_loop())
        else:
            metrics_task = None

        # TODO вынести в отдельный блок
        self._logger.info("Стартовая загрузка устройств из ValKey...")
        initial_devices = await self._repository.load_all_active_configs()
        for dev in initial_devices:
            await self._registry.add_or_update(dev)
        self._logger.info("найдено устройств: %s", len(initial_devices))

        try:
            await self._loop()
        except asyncio.CancelledError:
            print("[Корутина] Была отменена из-за сигнала")
            # Можно обработать отмену здесь, если нужно
            raise
        finally:
            sm_task.cancel()
            listener_task.cancel()
            command_loop.cancel()

            if metrics_task:
                metrics_task.cancel()

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

    async def _consume_commands_loop(self) -> None:
        """Единый обработчик команд мутации состояния (онлайн, офлайн, завершение сбора)."""
        while True:
            cmd = await self._command_queue.get()
            try:
                if isinstance(cmd, DeviceCreatedCommand):
                    await self._handle_device_created(cmd.device_uid)

                elif isinstance(cmd, DeviceUpdatedCommand):
                    await self._handle_device_updated(cmd.device_uid)

                elif isinstance(cmd, DeviceDeletedCommand):
                    await self._handle_device_deleted(cmd.device_uid)

            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Ошибка при обработке внутренней команды: %s", cmd)
            finally:
                self._command_queue.task_done()

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

    async def _handle_device_created(self, device_uid: str) -> None:
        dev = await self._repository.get_device_config(device_uid)
        if dev is None:
            self._logger.error("")
            return

        await self._registry.add_or_update(dev)
        self._logger.info(
            "Устройство %s добавлено в реестр.",
            device_uid,
        )

    async def _handle_device_updated(self, device_uid: str) -> None:
        # TODO копипаста created
        dev = await self._repository.get_device_config(device_uid)
        if dev is None:
            self._logger.error("")
            return

        await self._registry.add_or_update(dev)
        await self._state_machine.device_updated(device_uid)
        self._logger.info(
            "Устройство %s обновлено в реестре.",
            device_uid,
        )

    async def _handle_device_deleted(self, device_uid: str) -> None:
        await self._registry.remove(device_uid)
        await self._state_machine.device_updated(device_uid)
        self._logger.info(
            "Устройство %s удалено из реестра.",
            device_uid,
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

        repository = DeviceConfigRepository(
            client,
            logger=logger,
        )

        # очередь, куда записываются результаты проб
        probe_result_queue: asyncio.Queue[DeviceProbeResult] = asyncio.Queue()
        # очередь для сброса результатов проб в ClickHouse
        probe_result_queue_store_ch: asyncio.Queue[DeviceProbeResult] = asyncio.Queue()
        # внутренняя очередь команд
        command_queue: asyncio.Queue = asyncio.Queue()

        bus_notifier = StatusBusNotifier(
            client,
            logger=logger,
        )
        state_machine = DeviceStateMachine(
            bus_notifier,
            probe_result_queue,
            logger=logger,
        )

        # icmp "проверялка"
        # TODO ее не надо так передавать, она зависит от конфига, но пока так
        checker = IcmpChecker(logger=logger)
        worker_pool = DeviceNetworkWorker(
            checker,
            [probe_result_queue, probe_result_queue_store_ch],
            logger=logger,
        )

        registry = DeviceRegistry()
        bus_listener = PollerBusListener(
            client,
            command_queue,
            # registry,
        )

        store_client = await get_client()
        store = Store(
            client=store_client,
            logger=logger,
        )
        tracker = ServiceLifecycleTracker(store, service_name="poller_service", logger=logger)

        ch_metrics_buffer = ClickHouseMetricsBuffer(
            result_queue=probe_result_queue_store_ch,
            ch_repo=store,
            logger=logger,
        )

        instance = cls(
            registry,
            state_machine,
            worker_pool,
            bus_listener,
            repository,
            command_queue=command_queue,
            metrics_buffer=ch_metrics_buffer,
            concurrency_limit=concurrency_limit,
            logger=logger,
        )

        try:
            async with tracker.track():
                yield instance
        finally:
            await client.aclose()
            await store_client.close()
