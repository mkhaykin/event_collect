# apps/poller/ch_buffer.py
import asyncio
import logging
from typing import List

from libs.null_logger import NullLogger
from libs.poller.models import DeviceProbeResult
from libs.store import Store


class ClickHouseMetricsBuffer:
    """Асинхронный накопитель временных рядов в ОЗУ для пакетной вставки в ClickHouse."""

    def __init__(
        self,
        result_queue: asyncio.Queue[DeviceProbeResult],
        ch_repo: Store,
        batch_size_limit: int = 1000,
        flush_interval_sec: float = 10.0,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._queue = result_queue
        self._repo = ch_repo
        self._batch_size_limit = batch_size_limit
        self._flush_interval_sec = flush_interval_sec
        self._buffer: List[DeviceProbeResult] = []

        self._lock = asyncio.Lock()

    async def start_loop(self) -> None:
        """Старт двух параллельных конвейеров: сборщика и таймера."""
        self._logger.info("Буфер метрик ClickHouse запущен.")

        # фоновый таймер принудительного сброса по времени
        timer_task = asyncio.create_task(self._flush_by_timer_loop())

        try:
            # основной цикл для сброса данных в кликхаус пачками
            while True:
                result = await self._queue.get()

                async with self._lock:
                    self._buffer.append(result)

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
        """Периодический фоновый таймер сброса данных."""
        while True:
            try:
                await asyncio.sleep(self._flush_interval_sec)

                async with self._lock:
                    if self._buffer:
                        self._logger.debug(
                            "Сброс метрик по таймеру (интервал %s сек истек)",
                            self._flush_interval_sec,
                        )
                        await self._flush_now_unlocked()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Ошибка в цикле таймера буфера ClickHouse: %s", e)

    async def _flush_now_unlocked(self) -> None:
        """Внутренний метод сброса (вызывать строго под self._lock)."""
        # TODO подумать, чтобы self._lock затащить сюда, но могут быть проблемы с вызовом
        chunk = self._buffer
        self._buffer = []

        try:
            await self._repo.store_probe_result(chunk)
        except Exception:
            self._logger.exception("Не удалось зафиксировать пакет метрик в ClickHouse")
