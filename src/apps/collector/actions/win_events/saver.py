# apps/collector/savers.py
import asyncio
import logging
from typing import List

from apps.collector.actions.win_events.event_flat import EventFlat
from apps.collector.actions.win_events.event_raw import EventRaw
from libs.null_logger import NullLogger
from libs.store import Store


class ClickHouseWinEventsSaver:
    """Фоновый синглтон-писатель логов Windows. Отвечает за Fan-In агрегацию, Flat-маппинг и Bulk."""

    def __init__(
        self,
        raw_queue: asyncio.Queue[EventRaw],
        ch_repo: Store,
        batch_size_limit: int = 1000,
        flush_interval_sec: float = 10.0,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._queue = raw_queue
        self._repo: Store = ch_repo
        self._batch_size_limit = batch_size_limit
        self._flush_interval_sec = flush_interval_sec
        self._buffer: List[EventFlat] = []
        self._lock = asyncio.Lock()

    async def start_loop(self) -> None:
        """Главный цикл выгребания очереди и пакетного сброса."""
        self._logger.info("Сейвер ClickHouseWinEventsSaver успешно запущен в фоновом цикле.")
        timer_task = asyncio.create_task(self._flush_by_timer_loop())

        try:
            while True:
                raw_event = await self._queue.get()
                # TODO данные перенести в ... куда-то, но не хардкодить!
                #  может ip определять в конструкторе? Но версию точно тут не взять ...
                flat_event = raw_event.to_flat(collector_host="127.0.0.1", script_version="0.0.1")

                async with self._lock:
                    self._buffer.append(flat_event)
                    if len(self._buffer) >= self._batch_size_limit:
                        await self._flush_now_unlocked()

                self._queue.task_done()
        except asyncio.CancelledError:
            timer_task.cancel()
            async with self._lock:
                if self._buffer:
                    await self._flush_now_unlocked()
            raise

    async def _flush_by_timer_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._flush_interval_sec)
                async with self._lock:
                    if self._buffer:
                        await self._flush_now_unlocked()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Ошибка таймера сейвера ClickHouse: %s", e)

    async def _flush_now_unlocked(self) -> None:
        chunk = self._buffer
        self._buffer = []
        try:
            # Сбрасываем пачку в ClickHouse
            await self._repo.store_events(chunk)
        except Exception:
            self._logger.exception("Не удалось зафиксировать пакет логов в ClickHouse")
