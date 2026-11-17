# apps/collector/scheduler.py
import logging
import time
from dataclasses import dataclass

from libs.null_logger import NullLogger


@dataclass
class JobInfo:
    next_run: float | int
    interval: float | int


class JobScheduler:
    # TODO подумать над тем, что сделать под многопоточку
    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        # Двухуровневый индекс: {device_uid: {task_uid: JobInfo}}
        self._jobs: dict[str, dict[str, JobInfo]] = {}
        # Множество запущенных в данный момент задач: {(device_uid, task_uid)}
        self._running: set[tuple[str, str]] = set()

    def register(
        self,
        device_uid: str,
        task_uid: str,
        interval: float,
        next_run: float | None = None,
    ) -> None:
        """Регистрируем расписание устройства."""
        if device_uid in self._jobs:
            self._logger.info("Смена расписания у %s", device_uid)

        if device_uid not in self._jobs:
            self._jobs[device_uid] = {}

        self._jobs[device_uid][task_uid] = JobInfo(next_run=next_run or time.time(), interval=interval)

    def _clear_running(self, device_uid: str) -> None:
        for device, task in self._running:
            if device == device_uid:
                self._running.discard((device_uid, task))

    def remove(self, device_uid: str, task_uid: str | None = None) -> None:
        """Удаляет устройство из расписания и списка запущенных."""
        if device_uid not in self._jobs:
            self._logger.warning("Повторное удаление устройства %s ...", device_uid)
            return

        if task_uid is None:
            self._clear_running(device_uid)
            self._jobs.pop(device_uid, None)
        else:
            self._running.discard((device_uid, task_uid))
            self._jobs[device_uid].pop(task_uid, None)

    def get_due_jobs(
        self,
        current_time: float | None = None,
    ) -> list[tuple[str, str]]:  # сделать класс device_uid, task_uid
        """
        Возвращает список UID, готовых к запуску (не запущенных прямо сейчас и чье время пришло).
        """
        current_time = current_time or time.time()
        result = []

        for device_uid, tasks in self._jobs.items():
            for task_uid, job in tasks.items():
                next_run = job.next_run
                if (
                    (device_uid, task_uid) not in self._running
                    and next_run is not None
                    and current_time >= next_run
                ):
                    result.append((device_uid, task_uid))

        return result

    def mark_started(self, device_uid: str, task_uid: str) -> None:
        """
        Ставит отметку 'running'.
        """
        self._running.add((device_uid, task_uid))

    def mark_finished(
        self,
        device_uid: str,
        task_uid: str,
        *,
        is_success: bool = True,
        retry_delay_sec: int | None = None,
        # TODO это вообще-то повтор на случай неуспеха, стоит переименовать или как=то подумать ...
    ) -> None:
        """
        Снимает отметку 'running'.
        Если задача провалилась (is_success=False) и устройство еще в расписании,
        сдвигает next_run на retry_delay_sec.
        """
        self._running.discard((device_uid, task_uid))

        tasks = self._jobs.pop(device_uid, None)
        if tasks is None:
            self._logger.warning("Задач по устройству %s уже нет", device_uid)
            return

        old_job = tasks.pop(task_uid, None)

        if old_job is None:
            self._logger.warning(
                "Задача %s по устройству %s уже не в расписании, не продлеваем",
                task_uid,
                device_uid,
            )
            return

        interval: float | int
        if not is_success and retry_delay_sec is not None:
            interval = retry_delay_sec
        else:
            interval = old_job.interval

        # if device_uid not self._jobs[device_uid]
        self._jobs.setdefault(device_uid, {})[task_uid] = JobInfo(
            next_run=time.time() + interval,
            interval=old_job.interval,
        )

    def seconds_until_next(self) -> float | None:
        """
        Считает минимальное время сна только по тем задачам, которые НЕ находятся в self._running.
        """
        earliest_run: float | int | None = None
        for device_uid, tasks in self._jobs.items():
            for task_uid, job in tasks.items():
                if (device_uid, task_uid) in self._running:
                    continue

                if earliest_run is None or earliest_run > job.next_run:
                    earliest_run = job.next_run

        if earliest_run is None:
            return None

        return max(0.0, earliest_run - time.time())
