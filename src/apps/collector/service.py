# apps/collector/service.py
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Self

from redis.asyncio import from_url
from redis.maint_notifications import MaintNotificationsConfig

from apps.collector.actions import DummyCollectAction
from apps.collector.listener import CollectorBusListener
from apps.collector.registry import DeviceOnlineRegistry
from apps.collector.runner import JobRunner
from apps.collector.scheduler import JobScheduler
from apps.collector.store import CollectorStatusStore
from apps.device_provider.repository import DeviceConfigRepository
from libs.collector.models import (
    DeviceOfflineCommand,
    DeviceOnlineCommand,
    JobFinishedCommand,
)
from libs.config import config
from libs.null_logger import NullLogger


class CollectorService:
    """по сути оркестратор процесса"""

    RETRY_DELAY_SEC: int = 60

    def __init__(  # noqa: PLR0913 PLR0917
        self,
        registry: DeviceOnlineRegistry,
        repository: DeviceConfigRepository,
        scheduler: JobScheduler,
        runner: JobRunner,
        internal_queue: asyncio.Queue[Any],
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
        self._queue = internal_queue

        self._wakeup_event = wakeup_event
        self._db_repo = db_repo
        self._listener = listener

    async def start_loop(self) -> None:
        """Основной цикл"""
        self._logger.info("%s started...", self.__class__.__name__)

        # запускаем фоновую вычитку данных из листенера
        consumer_task = asyncio.create_task(self._consume_commands_loop())
        # слушатель
        listener_task = asyncio.create_task(self._listener.listen_forever())

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
                    await self._handle_device_online(cmd.uid)

                elif isinstance(cmd, DeviceOfflineCommand):
                    await self._handle_device_offline(cmd.uid)

                elif isinstance(cmd, JobFinishedCommand):
                    self._scheduler.mark_finished(
                        cmd.uid,
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

    async def _handle_device_online(self, uid: str) -> None:
        device = await self._repository.get_device_config(uid)
        if not device:
            return

        await self._db_repo.log_status_change(uid, "ONLINE")
        await self._registry.add_or_update(device)
        # Переводим минуты из конфига в секунды для шедулера
        self._scheduler.register(uid, interval=device.collect_interval_min * 60)
        self._logger.info(
            "Устройство %s поставлено на сбор (интервал: %s мин)",
            uid,
            device.collect_interval_min,
        )

    async def _handle_device_offline(self, uid: str) -> None:
        await self._db_repo.log_status_change(uid, "OFFLINE")
        await self._registry.remove(uid)
        self._scheduler.remove(uid)
        self._logger.info("Устройство %s снято со сбора", uid)

    async def _loop(self) -> None:
        while True:
            due_uids = self._scheduler.get_due_jobs()

            for uid in due_uids:
                device = await self._registry.get(uid)
                if device:
                    self._scheduler.mark_started(uid)
                    self._runner.dispatch(device)
                else:
                    self._logger.error(
                        "Не нашли конфигурацию устройства %s в репозитории, пропускаем обработку",
                        uid,
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

        client = await from_url(
            valkey_dsn,
            decode_responses=True,
            socket_timeout=None,
            socket_keepalive=True,
            maint_notifications_config=MaintNotificationsConfig(enabled=False),
        )

        # событие для подъема основного потока из ожидания
        wakeup_event = asyncio.Event()
        # очередь от листенера до основного потока
        internal_queue: asyncio.Queue[Any] = asyncio.Queue()

        # пока пустышка (потом PS)
        action_plugin = DummyCollectAction(logger=logger)
        # пока пустышка, потом сохранять инфу в БД
        db_repo = CollectorStatusStore(logger=logger)

        registry = DeviceOnlineRegistry(logger=logger)

        # стартует задачи, контролирует расписание
        scheduler = JobScheduler(
            logger=logger,
        )

        # листенер, подписан на события поллера (online|offline)
        bus_listener = CollectorBusListener(
            client,
            internal_queue=internal_queue,
            logger=logger,
        )

        runner = JobRunner(
            action=action_plugin,
            internal_queue=internal_queue,
            concurrency_limit=concurrency_limit,
            logger=logger,
        )

        config_repository = DeviceConfigRepository(client, logger=logger)

        # само ядро
        engine = cls(
            repository=config_repository,
            registry=registry,
            scheduler=scheduler,
            runner=runner,
            db_repo=db_repo,
            internal_queue=internal_queue,
            wakeup_event=wakeup_event,
            listener=bus_listener,
            logger=logger,
        )

        try:
            yield engine
        finally:
            await client.aclose()
