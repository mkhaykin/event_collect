# apps/collector/scheduler.py
import asyncio
import logging
import time
from typing import Optional

from apps.collector.actions import CollectAction
from apps.collector.registry import DeviceOnlineRegistry
from libs.collector.models import CollectResult
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class JobScheduler:
    """Активный планировщик задач. Хозяин Реестра ОЗУ и расписания сборов."""

    def __init__(
        self,
        action: CollectAction,
        registry: DeviceOnlineRegistry,
        wakeup_event: asyncio.Event,
        concurrency_limit: int = 20,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._action = action
        self._wakeup_event = wakeup_event
        self._semaphore = asyncio.Semaphore(concurrency_limit)

        self._registry: DeviceOnlineRegistry = registry
        self._schedule: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def add_device(self, device: DeviceConfig) -> None:
        async with self._lock:
            await self._registry.add_or_update(device)
            # первый запуск: планируем немедленно (страхуемся от повторного добавления)
            self._schedule[device.uid] = self._schedule.get(device.uid, time.time())

    async def remove_device(self, uid: str) -> None:
        async with self._lock:
            await self._registry.remove(uid)
            self._schedule.pop(uid, None)

    async def trigger_and_schedule_next(self) -> Optional[float]:
        """
        Сканирует расписание, оптимистично сдвигает таймеры вперед,
        выстреливает фоновыми воркерами и возвращает время сна для Движка.
        """
        async with self._lock:
            current_time = time.time()

            for dev in await self._registry.get_snapshot():
                next_run = self._schedule.get(dev.uid)
                if next_run is not None and current_time >= next_run:
                    # 1. ОПТИМИСТИЧНЫЙ СДВИГ: сразу переносим запуск в будущее до выстрела таски!
                    self._schedule[dev.uid] = current_time + (dev.collect_interval_min * 60)
                    self._logger.info(
                        "Следующий запуск задачи %s поставлен на +%s мин",
                        dev.uid,
                        dev.collect_interval_min,
                    )

                    # запуск фоновой
                    asyncio.create_task(self._safe_execute_launcher(dev))

            # возвращаем остаток времени до следующего запуска
            if not self._schedule:
                return None
            earliest_timestamp = min(self._schedule.values())
            remaining = earliest_timestamp - time.time()
            return max(0.0, remaining)

    async def _safe_execute_launcher(self, device: DeviceConfig) -> None:
        """Изолированный воркер. При ошибках реактивно корректирует расписание поближе."""
        async with self._semaphore:
            try:
                result: CollectResult = await self._action.execute(device)

                if result.is_success:
                    self._logger.info("Метрики успешно собраны для устройства %s", device.uid)
                else:
                    # Реактивная коррекция: если упал, пересчитываем на быстрый повтор
                    async with self._lock:
                        if device.uid in self._registry:  # Проверяем, что его не удалили пока он опрашивался
                            self._schedule[device.uid] = time.time() + 60
                    self._logger.warning("Сбор для %s провалился. Повтор назначен через 60с.", device.uid)
                    self._wakeup_event.set()  # Будим Движок

            except Exception:
                self._logger.exception("критический краш Action для %s", device.uid)
                async with self._lock:
                    if device.uid in self._schedule:
                        self._schedule[device.uid] = time.time() + 60
                self._wakeup_event.set()
