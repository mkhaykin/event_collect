# apps/collector/engine.py
import asyncio
import logging
from typing import Any

from apps.collector.repository import CollectorDummyRepository
from apps.collector.scheduler import JobScheduler
from libs.collector.models import DeviceOfflineCommand, DeviceOnlineCommand
from libs.null_logger import NullLogger


class CollectorCoreEngine:
    """по сути оркестратор процесса"""

    def __init__(
        self,
        scheduler: JobScheduler,
        internal_queue: asyncio.Queue[Any],
        wakeup_event: asyncio.Event,
        db_repo: CollectorDummyRepository,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._scheduler = scheduler
        self._queue = internal_queue
        self._wakeup_event = wakeup_event
        self._consumer_task: asyncio.Task[None] | None = None
        self._db_repo = db_repo

    async def start_orchestration(self) -> None:
        """Основной цикл"""
        self._logger.info("%s started...", self.__class__.__name__)

        # запускаем фоновую вычитку данных из листенера
        self._consumer_task = asyncio.create_task(self._consume_internal_events())

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

    async def stop(self) -> None:
        if self._consumer_task:
            self._consumer_task.cancel()

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
