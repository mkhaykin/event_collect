import asyncio
import logging

from libs.models.config import DeviceConfig
from libs.models.task import TaskDescription
from libs.null_logger import NullLogger


class TaskRegistry:
    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._lock = asyncio.Lock()

        self._devices: dict[str, set[str]] = {}
        self._tasks: dict[str, TaskDescription] = {}

    async def add_or_update(self, device: DeviceConfig) -> None:
        self._logger.debug("Регистрируем устройство %s", device.uid)
        async with self._lock:
            collectors = device.get_collectors()
            for item in collectors:
                self._devices.setdefault(device.uid, set()).add(item.uid)
                self._tasks[item.uid] = item

        self._logger.debug(
            "По устройству %s добавили %s сборщиков",
            device.uid,
            len(collectors),
        )

    async def remove(self, device_uid: str) -> None:
        if device_uid not in self._devices:
            self._logger.debug("Устройство %s не зарегистрировано, игнорируем удаление", device_uid)
            return

        self._logger.debug("Устройство %s к удалению", device_uid)
        async with self._lock:
            count = self._devices[device_uid]
            for task_uid in self._devices[device_uid]:
                self._tasks.pop(task_uid, None)

            self._devices.pop(device_uid, None)

        self._logger.debug(
            "По устройству %s убрали %s сборщиков",
            device_uid,
            count,
        )

    async def get_task(self, task_uid: str) -> TaskDescription | None:
        async with self._lock:
            return self._tasks.get(task_uid)

    async def get_tasks(self, device_uid: str) -> tuple[TaskDescription, ...]:
        async with self._lock:
            return tuple(self._tasks[uid] for uid in self._devices.get(device_uid, []))

    # async def add_or_update(self, task: TaskDescription) -> None:
    #     async with self._lock:
    #         pass
    #
    # async def remove(self, task: TaskDescription) -> None:
    #     async with self._lock:
    #         pass
