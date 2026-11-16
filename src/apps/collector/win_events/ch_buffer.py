# apps/collector/win_events/ch_buffer.py
import asyncio
import logging
from typing import List

from apps.collector.win_events.event_flat import EventFlat
from libs.null_logger import NullLogger
from libs.store import Store


class ClickHouseWinEventBuffer:
    """Асинхронный накопитель событий для пакетной вставки в ClickHouse."""

    def __init__(
        self,
        ch_repo: Store,
        batch_size_limit: int = 1000,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._repo = ch_repo
        self._batch_size_limit = batch_size_limit
        self._buffer: List[EventFlat] = []

        self._lock = asyncio.Lock()

    async def add(self, item: EventFlat) -> None:
        """Добавляет элемент в буфер в ОЗУ. Вызывается напрямую из WinEventsCollectAction."""
        async with self._lock:
            self._buffer.append(item)
            if len(self._buffer) >= self._batch_size_limit:
                await self._flush_now_unlocked()

    async def flush(self) -> None:
        """Принудительно смывает ВСЕ оставшиеся в буфере данные на диск."""
        async with self._lock:
            if self._buffer:
                self._logger.debug(
                    "Принудительный Flush остатков буфера ClickHouse. Размер: %s",
                    len(self._buffer),
                )
                await self._flush_now_unlocked()

    async def _flush_now_unlocked(self) -> None:
        """Внутренний метод сброса (вызывать строго под self._lock)."""
        # TODO подумать, чтобы self._lock затащить сюда, но могут быть проблемы с вызовом
        chunk = self._buffer
        self._buffer = []

        try:
            await self._repo.store_events(chunk)
        except Exception:
            self._logger.exception("Не удалось зафиксировать пакет метрик в ClickHouse")
