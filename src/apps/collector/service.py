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
from apps.collector.repository import CollectorDummyRepository
from apps.collector.scheduler import JobScheduler
from libs.collector.models import DeviceOfflineCommand, DeviceOnlineCommand
from libs.null_logger import NullLogger


class CollectorService:
    """по сути оркестратор процесса"""

    def __init__(  # noqa: PLR0913
        self,
        scheduler: JobScheduler,
        internal_queue: asyncio.Queue[Any],
        wakeup_event: asyncio.Event,
        db_repo: CollectorDummyRepository,
        listener: CollectorBusListener,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._scheduler = scheduler
        self._queue = internal_queue
        self._wakeup_event = wakeup_event
        self._db_repo = db_repo
        self._listener = listener

    async def start_loop(self) -> None:
        """Основной цикл"""
        self._logger.info("%s started...", self.__class__.__name__)

        # запускаем фоновую вычитку данных из листенера
        consumer_task = asyncio.create_task(self._consume_internal_events())
        # слушатель
        listener_task = asyncio.create_task(self._listener.listen_forever())

        try:
            await self._loop()
        finally:
            consumer_task.cancel()
            listener_task.cancel()

    async def _loop(self) -> None:
        while True:
            # определяем время сна
            wait_timeout = await self._scheduler.trigger_and_schedule_next()
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

    async def _consume_internal_events(self) -> None:
        """ловим события от листенера и добавляем/удаляем устройства из шедулера"""
        while True:
            cmd = await self._queue.get()
            try:
                if isinstance(cmd, DeviceOnlineCommand):
                    await self._scheduler.add_device(cmd.device)
                    await self._db_repo.log_status_change(cmd.device.uid, "ONLINE")

                    self._logger.info(
                        "%s: Устройство %s поставлено на сбор.",
                        self.__class__.__name__,
                        cmd.device.uid,
                    )

                elif isinstance(cmd, DeviceOfflineCommand):
                    await self._scheduler.remove_device(cmd.uid)
                    await self._db_repo.log_status_change(cmd.uid, "OFFLINE")

                    self._logger.info(
                        "%s: Устройство %s снято со сбора.",
                        self.__class__.__name__,
                        cmd.uid,
                    )
                # будим основной поток цикла
                self._wakeup_event.set()
            except Exception:
                self._logger.exception(
                    "%s: ошибка разбора внутренней команды диспетчером",
                    self.__class__.__name__,
                )
            finally:
                self._queue.task_done()

    @classmethod
    @asynccontextmanager
    async def factory(
        cls,
        valkey_dsn: str,
        *,
        logger: logging.Logger | None = None,
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
        # очередь от листера до основного потока
        internal_queue: asyncio.Queue[Any] = asyncio.Queue()

        # пока пустышка (потом PS)
        action_plugin = DummyCollectAction(logger=logger)
        # пока пустышка, потом сохранять инфу в БД
        db_repo = CollectorDummyRepository(logger=logger)

        registry = DeviceOnlineRegistry(logger=logger)

        # стартует задачи, контролирует расписание
        scheduler = JobScheduler(
            action=action_plugin,
            registry=registry,
            wakeup_event=wakeup_event,
            concurrency_limit=20,
            logger=logger,
        )

        # листенер, подписан на события поллера (online|offline)
        bus_listener = CollectorBusListener(
            client,
            internal_queue=internal_queue,
            logger=logger,
        )

        # само ядро
        engine = cls(
            scheduler=scheduler,
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
