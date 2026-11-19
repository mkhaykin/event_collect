# apps/collector/scheduler.py
import logging
import time
from dataclasses import dataclass

from libs.models.task import TaskDescription
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

        # что и когда запускаем
        self._jobs: dict[str, JobInfo] = {}
        # множество запущенных в данный момент задач
        self._running: set[str] = set()

    def register(
        self,
        task: TaskDescription,
    ) -> None:
        """Регистрируем расписание устройства."""
        if task.uid in self._jobs:
            self._logger.info("Повторная регистрация, смена расписания у %s", task.uid)
            # тут бы по честному пересчитать расписание, но не понятно как ...

        self._jobs[task.uid] = JobInfo(next_run=time.time(), interval=task.interval_sec)

    def remove(self, task_uid: str) -> None:
        """Удаляет устройство из расписания и списка запущенных."""
        if task_uid not in self._jobs:
            self._logger.warning("Повторное удаление таски %s ...", task_uid)
            return

        self._running.discard(task_uid)
        self._jobs.pop(task_uid, None)

    def get_due_jobs(
        self,
        current_time: float | None = None,
    ) -> list[str]:
        """
        Возвращает список UID, готовых к запуску (не запущенных прямо сейчас и чье время пришло).
        """
        current_time = current_time or time.time()
        result = []

        for task_uid, job in self._jobs.items():
            next_run = job.next_run
            if task_uid not in self._running and next_run is not None and current_time >= next_run:
                result.append(task_uid)

        return result

    def mark_started(self, task_uid: str) -> None:
        """
        Ставит отметку 'running'.
        """
        self._running.add(task_uid)

    def mark_finished(
        self,
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
        self._running.discard(task_uid)

        task = self._jobs.pop(task_uid, None)
        if task is None:
            self._logger.warning(
                "Задача %s уже не в расписании, не продлеваем",
                task_uid,
            )
            return

        interval: float | int
        if not is_success and retry_delay_sec is not None:
            interval = retry_delay_sec
        else:
            interval = task.interval

        self._jobs[task_uid] = JobInfo(
            next_run=time.time() + interval,
            interval=task.interval,
        )

    def seconds_until_next(self) -> float | None:
        """
        Считает минимальное время сна только по тем задачам, которые НЕ находятся в self._running.
        """
        earliest_run: float | int | None = None

        for task_uid, job in self._jobs.items():
            if task_uid in self._running:
                continue

            if earliest_run is None or earliest_run > job.next_run:
                earliest_run = job.next_run

        if earliest_run is None:
            return None

        return max(0.0, earliest_run - time.time())

    def __contains__(self, task_uid: str) -> bool:
        return task_uid in self._jobs
