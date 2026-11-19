# apps/collector/service.py
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Self

from redis.asyncio import from_url
from redis.maint_notifications import MaintNotificationsConfig

from apps.collector.actions.base import BaseCollectAction
from apps.collector.actions.win_events.actions import WinEventsCollectAction
from apps.collector.actions.win_events.saver import ClickHouseWinEventsSaver
from apps.collector.listener import CollectorBusListener
from apps.collector.runner import JobRunner
from apps.collector.scheduler import JobScheduler
from apps.collector.store import CollectorStatusStore
from apps.collector.task_registry import TaskRegistry
from apps.device_provider.repository import DeviceConfigRepository
from libs.collector.models import (
    DeviceOfflineCommand,
    DeviceOnlineCommand,
    DeviceUpdatedCommand,
    JobFinishedCommand,
)
from libs.config import config
from libs.null_logger import NullLogger
from libs.service_tracker import ServiceLifecycleTracker
from libs.store import Store, get_client


class CollectorService:
    """по сути оркестратор процесса"""

    RETRY_DELAY_SEC: int = 60

    def __init__(  # noqa: PLR0913 PLR0917
        self,
        registry: TaskRegistry,
        repository: DeviceConfigRepository,  # valkey_repo
        scheduler: JobScheduler,
        runner: JobRunner,
        command_queue: asyncio.Queue[Any],
        wakeup_event: asyncio.Event,
        db_repo: CollectorStatusStore,
        listener: CollectorBusListener,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._registry = registry
        self._repository = repository

        self._scheduler = scheduler
        self._runner = runner
        self._queue = command_queue

        self._wakeup_event = wakeup_event
        self._db_repo = db_repo
        self._listener = listener

    async def start_loop(self) -> None:
        """Основной цикл"""
        # слушатель
        listener_task = asyncio.create_task(self._listener.listen_forever())
        # запускаем фоновую вычитку данных из листенера
        consumer_task = asyncio.create_task(self._consume_commands_loop())

        try:
            await self._loop()
        finally:
            consumer_task.cancel()
            listener_task.cancel()
            await asyncio.gather(listener_task, consumer_task, return_exceptions=True)

    async def _consume_commands_loop(self) -> None:
        """Единый обработчик команд мутации состояния (онлайн, офлайн, завершение сбора)."""
        while True:
            cmd = await self._queue.get()
            try:
                if isinstance(cmd, DeviceOnlineCommand):
                    await self._handle_device_online(cmd.device_uid)

                elif isinstance(cmd, DeviceOfflineCommand):
                    await self._handle_device_offline(cmd.device_uid)

                elif isinstance(cmd, DeviceUpdatedCommand):
                    if cmd.device_uid in self._scheduler:
                        self._logger.debug("Устройство изменено, сначала offline, потом online")
                        await self._handle_device_offline(cmd.device_uid)
                        await self._handle_device_online(cmd.device_uid)
                    else:
                        self._logger.debug("Устройство %s не в графике коллектора, игнорируем")

                elif isinstance(cmd, JobFinishedCommand):
                    self._scheduler.mark_finished(
                        # cmd.device_uid,
                        cmd.task_uid,
                        is_success=cmd.is_success,
                        retry_delay_sec=self.RETRY_DELAY_SEC,
                    )

                # Любое изменение состояния требует перерасчета времени сна основного цикла
                self._wakeup_event.set()

            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Ошибка при обработке внутренней команды: %s", cmd)
            finally:
                self._queue.task_done()

    async def _handle_device_online(self, device_uid: str) -> None:
        device = await self._repository.get_device_config(device_uid)
        if not device:
            return

        await self._db_repo.log_status_change(device_uid, "ONLINE")
        await self._registry.add_or_update(device)

        tasks = device.get_collectors()
        if not tasks:
            self._logger.warning("Устройство %s онлайн, collectors пуст, сбор игнорируется", device_uid)
            return

        for task in tasks:
            # Переводим минуты из конфига в секунды для шедулера
            self._scheduler.register(task)
            self._logger.info(
                "Устройство %s поставлено на сбор (интервал: %s сек)",
                device_uid,
                task.interval_sec,
            )

    async def _handle_device_offline(self, uid: str) -> None:
        await self._db_repo.log_status_change(uid, "OFFLINE")

        for task in await self._registry.get_tasks(uid):
            self._logger.info("Удаляем задачу %s из расписания", task.uid)
            self._scheduler.remove(task.uid)
        await self._registry.remove(uid)

    async def _loop(self) -> None:
        while True:
            due_task_uids = self._scheduler.get_due_jobs()

            for task_uid in due_task_uids:
                task = await self._registry.get_task(task_uid)
                if task:
                    self._scheduler.mark_started(task_uid)
                    self._runner.dispatch(task)
                else:
                    self._logger.error(
                        "Не нашли конфигурацию таска %s, пропускаем обработку",
                        task_uid,
                    )

            # определяем время сна
            wait_timeout = self._scheduler.seconds_until_next()
            self._wakeup_event.clear()

            if wait_timeout is None:
                self._logger.debug(
                    "%s: расписание пусто. ждем-с...",
                    self.__class__.__name__,
                )
                await self._wakeup_event.wait()
            else:
                try:
                    self._logger.debug(
                        "%s: спать на %.2f сек...",
                        self.__class__.__name__,
                        wait_timeout,
                    )
                    await asyncio.wait_for(self._wakeup_event.wait(), timeout=wait_timeout)
                except asyncio.TimeoutError:
                    continue

    @classmethod
    @asynccontextmanager
    async def factory(
        cls,
        valkey_dsn: str,
        *,
        logger: logging.Logger | None = None,
        concurrency_limit: int = config.CONCURRENCY_LIMIT,
    ) -> AsyncGenerator[Self, None]:

        valkey_client = await from_url(
            valkey_dsn,
            decode_responses=True,
            socket_timeout=None,
            socket_keepalive=True,
            maint_notifications_config=MaintNotificationsConfig(enabled=False),
        )

        store_client = await get_client()
        store = Store(
            client=store_client,
            logger=logger,
        )
        tracker = ServiceLifecycleTracker(store, service_name="collector_service", logger=logger)

        # событие для подъема основного потока из ожидания
        wakeup_event = asyncio.Event()
        # очередь от листенера до основного потока
        internal_queue: asyncio.Queue[Any] = asyncio.Queue()
        # отдельная очередь для событий журнала
        win_events_queue: asyncio.Queue[Any] = asyncio.Queue()

        win_events_saver = ClickHouseWinEventsSaver(win_events_queue, store, logger=logger)
        win_saver_task = asyncio.create_task(win_events_saver.start_loop())

        plugin_registry: dict[str, type[BaseCollectAction]] = {
            "win_events": WinEventsCollectAction,
        }
        queues_registry: dict[str, asyncio.Queue] = {
            "win_events": win_events_queue,
        }

        db_repo = CollectorStatusStore(logger=logger)

        # листенер, подписан на события поллера (online|offline)
        bus_listener = CollectorBusListener(
            valkey_client,
            internal_queue=internal_queue,
            logger=logger,
        )

        runner = JobRunner(
            # TODO убираем плагины и очереди, делаем Фабрику плагинов
            plugin_registry,
            queues_registry,
            command_queue=internal_queue,
            concurrency_limit=concurrency_limit,
            logger=logger,
        )

        config_repository = DeviceConfigRepository(valkey_client, logger=logger)

        service = cls(
            repository=config_repository,
            # ведет реест задач
            registry=TaskRegistry(logger=logger),
            # стартует задачи, контролирует расписание
            scheduler=JobScheduler(
                logger=logger,
            ),
            runner=runner,
            db_repo=db_repo,
            command_queue=internal_queue,
            wakeup_event=wakeup_event,
            listener=bus_listener,
            logger=logger,
        )

        try:
            async with tracker.track():
                yield service
        finally:
            win_saver_task.cancel()

            await valkey_client.aclose()
            await store_client.close()
