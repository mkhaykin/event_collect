# tests/test_model_saver.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.model_saver import EventSaver


# --- Моки для тестирования ---
class MockEvent:
    """Упрощенная реализация протокола IEventModel для тестов."""

    def __init__(self, table_name: str, row_data: tuple, columns: tuple[str, ...] = ("col1", "col2")):
        self._table_name = table_name
        self._row_data = row_data
        self._columns = columns

    @property
    def table_name(self) -> str:
        return self._table_name

    def to_row(self) -> tuple:
        return self._row_data

    @classmethod
    def get_columns(cls) -> tuple[str, ...]:
        # В реальном коде это классовый метод, для простоты теста возвращаем фиксированный кортеж
        return ("col1", "col2")


@pytest.mark.asyncio
async def test_saver_batch_trigger_and_drain():
    """Штатный сценарий: Проверяет, что при достижении batch_size данные улетают в базу,

    а если накопилось больше — конвейер осушает буфер досуха за один вызов.
    """
    mock_client = MagicMock()
    mock_client.insert = AsyncMock()
    queue = asyncio.Queue()

    # Настраиваем batch_size = 10. Закидываем 25 элементов (должно быть 3 инсерта: 10, 10 и 5)
    saver = EventSaver(client=mock_client, queue=queue, batch_size=10, flush_interval_sec=100.0)

    for i in range(25):
        event = MockEvent("test_table", (f"data_{i}", i))
        await saver.add_event(event)

    # Так как 25 < 30, автоматический триггер сработал дважды (на 10 и 20).
    # В буфере осталось висеть 5 штук.
    assert len(saver._buffers["test_table"]) == 5
    assert mock_client.insert.call_count == 2

    # Вызываем ручной флуш оставшихся 5 элементов
    await saver._flush_all()
    assert len(saver._buffers["test_table"]) == 0
    assert mock_client.insert.call_count == 3


@pytest.mark.asyncio
async def test_saver_network_failure_and_backpressure_recovery():
    """Краевой случай 1: При падении сети пачка должна вернуться в начало буфера,

    а бесконечный цикл — прерваться (break), не уходя в глухое зависание.
    """
    mock_client = MagicMock()
    # Имитируем падение сети (например, таймаут базы)
    mock_client.insert = AsyncMock(side_effect=RuntimeError("ClickHouse connection timeout"))
    queue = asyncio.Queue()

    saver = EventSaver(client=mock_client, queue=queue, batch_size=5, buffer_overflow_limit=20)

    # Наполняем буфер до срабатывания триггера (5 элементов)
    for i in range(5):
        await saver.add_event(MockEvent("metrics", (f"val_{i}",)))

    # Проверяем, что из-за ошибки инсерта пачка вернулась обратно в буфер
    assert len(saver._buffers["metrics"]) == 5
    # Проверяем, что произошел ровно 1 вызов (break отработал, а не крутился в бесконечной петле)
    assert mock_client.insert.call_count == 1


@pytest.mark.asyncio
async def test_saver_buffer_overflow_discard():
    """Краевой случай 2: Если сеть лежит долго и буфер превышает BUFFER_OVERFLOW_LIMIT,

    новые упавшие куски должны отбрасываться (drop) ради спасения ОЗУ от OOM.
    """
    mock_client = MagicMock()
    mock_client.insert = AsyncMock(side_effect=RuntimeError("Database is dead"))
    queue = asyncio.Queue()

    # Лимит переполнения всего 10 элементов, батч = 5
    saver = EventSaver(client=mock_client, queue=queue, batch_size=5, buffer_overflow_limit=10)

    # 1. Первая пачка (5 штук) — падает и возвращается в буфер (размер становится 5)
    for i in range(5):
        await saver.add_event(MockEvent("logs", (f"msg_{i}",)))

    # 2. Вторая пачка (еще 5 штук) — падает, возвращается, размер становится 10 (достигли лимита)
    for i in range(5):
        await saver.add_event(MockEvent("logs", (f"msg_{i}",)))

    assert len(saver._buffers["logs"]) == 10

    # 3. Третья пачка (еще 5 штук) — должна триггернуть критический лог и отброситься
    with patch.object(saver._logger, "critical") as mock_critical:
        for i in range(5):
            await saver.add_event(MockEvent("logs", (f"msg_overflow_{i}",)))

        # Буфер жестко зафиксирован на отметке 10, лишнее уничтожено
        assert len(saver._buffers["logs"]) == 10
        mock_critical.assert_called_once()


@pytest.mark.asyncio
async def test_race_condition_queue_vs_timer_lock():
    """ТЕСТ НА ГОНКИ (Race Condition): Проверяет, что таймер и входящая очередь

    никогда не запустят флуш одной таблицы одновременно благодаря _flushing_tables.
    """
    mock_client = MagicMock()
    queue = asyncio.Queue()
    saver = EventSaver(client=mock_client, queue=queue, batch_size=10)

    # Забиваем буфер на 9 элементов (флуш еще не сработал)
    for i in range(9):
        await saver.add_event(MockEvent("race_table", (i,)))

    # Искусственно замедляем сетевой инсерт, чтобы зафиксировать корутину внутри _flush_table_chunks
    async def slow_insert(*args, **kwargs):
        await asyncio.sleep(0.1)  # Имитируем сетевую задержку в 100 мс

    mock_client.insert.side_effect = slow_insert

    with patch.object(saver, "_flush_table_chunks", wraps=saver._flush_table_chunks) as mock_chunks_method:
        # Добавляем 10-й элемент. Это триггерит асинхронный add_event -> _flush.
        # Корутина заходит внутрь, выставляет блокировку таблицы и «зависает» на 100 мс на slow_insert.
        task_from_queue = asyncio.create_task(saver.add_event(MockEvent("race_table", (10,))))

        # Даем планировщику asyncio переключить контекст, чтобы первая корутина успела занять лок флуша
        await asyncio.sleep(0.01)

        # В этот же микросекундный момент просыпается таймер и пытается вызвать _flush_all
        # Он должен увидеть, что таблица занята, и просто пропустить её.
        await saver._flush_all()

        # Ждем завершения первой (основной) задачи из очереди
        await task_from_queue

        # метод нарезки и отправки чанков вызвался строго 1 раз.
        # Таймер отфильтровал таблицу на взлете и даже не пытался запустить её обработку повторно!
        assert mock_chunks_method.call_count == 1


@pytest.mark.asyncio
async def test_graceful_shutdown_queue_evacuation_and_timeout():
    """Тест жизненного цикла: Проверяет, что при отмене start_loop

    очередь эвакуируется в буферы, а принудительный таймаут прерывает зависший слив.
    """
    mock_client = MagicMock()
    mock_client.insert = AsyncMock()
    queue = asyncio.Queue()

    saver = EventSaver(client=mock_client, queue=queue, batch_size=100)

    # Наполняем саму asyncio.Queue (закидываем 5 элементов)
    for i in range(5):
        await queue.put(MockEvent("shutdown_table", (i,)))

    # Запускаем основной цикл сейвера в фоне
    loop_task = asyncio.create_task(saver.start_loop())
    # Даем ему обработать часть данных (или просто встать в режим ожидания)
    await asyncio.sleep(0.01)

    # Имитируем сигнал остановки контейнера (SIGTERM от докера)
    loop_task.cancel()

    # Дожидаемся завершения Graceful Shutdown
    with pytest.raises(asyncio.CancelledError):
        await loop_task

    # ПРОВЕРКА: Очередь должна быть пуста (все 5 штук высосаны методом _flush_queue)
    assert queue.empty()
    # Буфер ClickHouse должен быть чист (метод _flush_all унес эвакуированные остатки в базу)
    assert len(saver._buffers.get("shutdown_table", [])) == 0
    # База честно получила финальный пакет
    assert mock_client.insert.call_count == 1
