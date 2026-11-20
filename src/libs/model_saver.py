# src/libs/model_saver.py
import asyncio
import logging
from asyncio import Lock
from typing import Any, Protocol, Sequence

from libs.null_logger import NullLogger

BATCH_SIZE = 1_000
BUFFER_OVERFLOW_LIMIT = 10_000
DEFAULT_FLUSH_INTERVAL_SEC = 10.0


class IEventModel(Protocol):
    @property
    def table_name(self) -> str: ...
    def to_row(self) -> tuple: ...

    @classmethod
    def get_columns(cls) -> tuple[str, ...]: ...


class ISaver(Protocol):
    async def insert(
        self,
        table: str | None = None,
        data: Sequence[Sequence[Any]] | None = None,
        column_names: str | Sequence[str] | None = "*",
    ) -> Any: ...


class EventSaver:
    def __init__(  # noqa: PLR0913
        self,
        client: ISaver,
        queue: asyncio.Queue[IEventModel],
        *,
        batch_size: int = BATCH_SIZE,
        buffer_overflow_limit: int = BUFFER_OVERFLOW_LIMIT,
        flush_interval_sec: float = DEFAULT_FLUSH_INTERVAL_SEC,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._client = client
        self._queue = queue

        self._batch_size = batch_size
        self._buffer_overflow_limit = buffer_overflow_limit
        self._flush_interval_sec = flush_interval_sec

        # описание колонок
        self._columns: dict[str, tuple[str, ...]] = {}
        # непосредственно буфера по таблицам
        self._buffers: dict[str, list[tuple[Any, ...]]] = {}

        # общий локер
        self._lock: Lock = Lock()
        # страховка от одновременного flush из _loop_queue и _loop_timer
        self._flushing_tables: set[str] = set()

    async def add_event(self, event: IEventModel) -> None:
        table_name: str | None
        async with self._lock:
            if event.table_name not in self._columns:
                self._columns[event.table_name] = event.get_columns()

            self._buffers.setdefault(event.table_name, []).append(event.to_row())
            table_name = event.table_name

            if len(self._buffers[event.table_name]) < self._batch_size:
                table_name = None

        if table_name:
            await self._flush(event.table_name)

    async def start_loop(self) -> None:
        task_queue = asyncio.create_task(self._loop_queue())
        task_timer = asyncio.create_task(self._loop_timer())
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            task_queue.cancel()
            task_timer.cancel()

            await asyncio.gather(task_queue, task_timer, return_exceptions=True)

            await self._flush_queue()
            await self._flush_all()
            raise

    async def _loop_queue(self) -> None:
        while True:
            try:
                raw_event = await self._queue.get()
                await self.add_event(raw_event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break

    async def _loop_timer(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._flush_interval_sec)
                await self._flush_all()
            except asyncio.CancelledError:
                break

    async def _flush_all(self) -> None:
        async with self._lock:
            tables = [
                table
                for table, data in self._buffers.items()
                if len(data) > 0 and table not in self._flushing_tables
            ]
        for table in tables:
            await self._flush(table)

    async def _flush(self, table_name: str) -> None:
        if not await self._set_table_flush_lock(table_name):
            return None

        try:
            return await self._flush_table_chunks(table_name)
        finally:
            await self._remove_table_flush_lock(table_name)

    async def _set_table_flush_lock(self, table_name: str) -> bool:
        async with self._lock:
            if table_name in self._flushing_tables:
                self._logger.warning(
                    "Concurrent call to flush on table %s. Skipped.",
                    table_name,
                )
                return False
            self._flushing_tables.add(table_name)
        return True

    async def _remove_table_flush_lock(self, table_name: str) -> None:
        async with self._lock:
            self._flushing_tables.discard(table_name)

    async def _flush_table_chunks(self, table_name: str) -> None:
        while True:
            async with self._lock:
                buffer = self._buffers.get(table_name, [])
                if not buffer:
                    return

                chunk = buffer[: self._batch_size]
                self._buffers[table_name] = buffer[self._batch_size :]

            try:
                self._logger.debug("Flushing %s, chunk_size %s", table_name, len(chunk))
                await self._client.insert(
                    table_name,
                    data=chunk,
                    column_names=self._columns[table_name],
                )
            except Exception:
                self._logger.exception("Failed to flush %s", table_name)

                async with self._lock:
                    current_buffered = self._buffers.get(table_name, [])
                    if len(current_buffered) + len(chunk) <= self._buffer_overflow_limit:
                        self._buffers[table_name] = chunk + current_buffered
                    else:
                        self._logger.critical(
                            "Table buffer overflow %s! %d rows discarded.",
                            table_name,
                            len(chunk),
                        )
                break

    async def _flush_queue(self) -> None:
        buffer: list[IEventModel] = []
        # формально тут мы можем превысить overflow_limit на конкретном буфере,
        # но это финальная очистка очереди, так что и бог с ней
        try:
            async with asyncio.timeout(2.0):  # Даем строго 2 секунды на эвакуацию данных
                while not self._queue.empty() and len(buffer) < self._buffer_overflow_limit:
                    try:
                        raw_event = self._queue.get_nowait()
                        buffer.append(raw_event)
                        self._queue.task_done()
                    except asyncio.QueueEmpty:
                        break
                    except Exception:
                        self._logger.exception("Flush queue exception")
        except TimeoutError:
            self._logger.exception("Flush queue timeout exception")

        async with self._lock:
            for item in buffer:
                if item.table_name not in self._columns:
                    self._columns[item.table_name] = item.get_columns()
                self._buffers.setdefault(item.table_name, []).append(item.to_row())
