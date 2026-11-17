# apps/collector/runner.py
import asyncio
import logging
from typing import Any

from apps.collector.actions.base import BaseCollectAction
from apps.collector.actions.interface import CollectAction
from apps.collector.actions.states.file_state_storage import FileStateStorage
from libs.collector.models import CollectResult, JobFinishedCommand
from libs.config import config
from libs.events.models import CollectorTaskConfig, DeviceConfig
from libs.null_logger import NullLogger


class JobRunner:
    """Изолированный исполнитель задач сбора данных с контролем конкурентности."""

    def __init__(
        self,
        # TODO все что ниже, можно в дефолты наверное, хотя как очереди в дефолты???
        plugin_registry: dict[str, type[BaseCollectAction]],  # классы коллекторов под типы задач
        queues_registry: dict[str, asyncio.Queue],  # список очередей под типы задач
        command_queue: asyncio.Queue[Any],  # TODO или очередь результата?
        concurrency_limit: int = config.CONCURRENCY_LIMIT,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._plugin_registry = plugin_registry
        self._queues_registry = queues_registry

        self._queue = command_queue
        self._semaphore = asyncio.Semaphore(concurrency_limit)

        # храним ссылки на активные задачи
        self._active_tasks: set[asyncio.Task[None]] = set()

    def dispatch(self, device: DeviceConfig, task: CollectorTaskConfig) -> None:
        """запуск задачи сбора для устройства."""
        plugin_class = self._plugin_registry.get(task.type)
        target_queue = self._queues_registry.get(task.type)

        if not plugin_class or target_queue is None:
            self._logger.error("Не найден плагин или очередь для типа задачи: %s", task.type)
            return

        t = asyncio.create_task(self._execute_safe(device, task, plugin_class, target_queue))
        self._active_tasks.add(t)
        t.add_done_callback(self._active_tasks.discard)

    async def _execute_safe(
        self,
        # task_id: str,  # TODO наверное uid ...
        device: DeviceConfig,
        task: CollectorTaskConfig,
        plugin_class: type[Any],
        target_queue: asyncio.Queue,
    ) -> None:
        """Собираем нужный Action, выполняем и бросаем команду завершения в очередь."""
        is_success = False
        result: CollectResult | None = None

        # TODO добавить try | except для
        action: CollectAction = plugin_class(
            queue=target_queue,
            state_storage=FileStateStorage(
                logger=self._logger,
            ),
            logger=self._logger,
            **task.params,
        )

        async with self._semaphore:
            try:
                result = await action.execute(device)
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
                # TODO пофиксить, и вынести отдельно RuntimeError("Не получили результат")
                # может через свой exception
                self._logger.exception("Непредвиденный сбой при выполнении сбора для %s", device.uid)
                is_success = False
            finally:
                # отправляем команду в очередь о завершении
                cmd = JobFinishedCommand(
                    device_uid=device.uid,
                    task_uid=task.uid,
                    is_success=is_success,
                    result=result,
                )
                await self._queue.put(cmd)
