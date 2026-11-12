# apps/collector/runner.py
import asyncio
import logging
from typing import Any

from apps.collector.actions import CollectAction
from libs.collector.models import CollectResult, JobFinishedCommand
from libs.config import config
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class JobRunner:
    """Изолированный исполнитель задач сбора данных с контролем конкурентности."""

    def __init__(
        self,
        action: CollectAction,
        internal_queue: asyncio.Queue[Any],
        concurrency_limit: int = config.CONCURRENCY_LIMIT,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._action = action
        self._queue = internal_queue
        self._semaphore = asyncio.Semaphore(concurrency_limit)

        # храним ссылки на активные задачи
        self._active_tasks: set[asyncio.Task[None]] = set()

    def dispatch(self, device: DeviceConfig) -> None:
        """запуск задачи сбора для устройства."""
        task = asyncio.create_task(self._execute_safe(device))
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    async def _execute_safe(self, device: DeviceConfig) -> None:
        """выполняем Action и бросаем команду завершения в очередь."""
        is_success = False
        result: CollectResult | None = None

        async with self._semaphore:
            try:
                result = await self._action.execute(device)
                if result is None:
                    # если не получили результат, то считаем, что ошибка исполнения
                    # (хотя это может и косяк реализации Action)
                    raise RuntimeError("Не получили результат")
                is_success = result.is_success

                if is_success:
                    self._logger.info("Сбор данных для %s завершен успешно", device.uid)
                else:
                    self._logger.warning(
                        "Сбор данных для %s завершился ошибкой: %s",
                        device.uid,
                        result.error_message,
                    )

            except asyncio.CancelledError:
                self._logger.info("Задача сбора для %s была отменена", device.uid)
                raise
            except Exception:
                self._logger.exception("Непредвиденный сбой при выполнении сбора для %s", device.uid)
                is_success = False
            finally:
                # отправляем команду в очередь о завершении
                cmd = JobFinishedCommand(
                    uid=device.uid,
                    is_success=is_success,
                    result=result,
                )
                await self._queue.put(cmd)
