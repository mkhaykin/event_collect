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

        self._jobs: dict[str, JobInfo] = {}
        self._running: set[str] = set()

    def register(
        self,
        uid: str,
        interval: float,
        next_run: float | None = None,
    ) -> None:
        """Регистрируем расписание устройства."""
        if uid in self._jobs:
            self._logger.info("Смена расписания у %s", uid)

        self._jobs[uid] = JobInfo(next_run=next_run or time.time(), interval=interval)

    def remove(self, uid: str) -> None:
        """Удаляет устройство из расписания и списка запущенных."""
        self._jobs.pop(uid, None)
        self._running.discard(uid)

    def get_due_jobs(self, current_time: float | None = None) -> list[str]:
        """
        Возвращает список UID, готовых к запуску (не запущенных прямо сейчас и чье время пришло).
        """
        current_time = current_time or time.time()
        result = []

        for uid, job in self._jobs.items():
            next_run = job.next_run
            if uid not in self._running and next_run is not None and current_time >= next_run:
                result.append(uid)

        return result

    def mark_started(self, uid: str) -> None:
        """
        Ставит отметку 'running'.
        """
        self._running.add(uid)

    def mark_finished(
        self,
        uid: str,
        *,
        is_success: bool = True,
        retry_delay_sec: int | None = None,
    ) -> None:
        """
        Снимает отметку 'running'.
        Если задача провалилась (is_success=False) и устройство еще в расписании,
        сдвигает next_run на retry_delay_sec.
        """
        self._running.discard(uid)
        old_job = self._jobs.pop(uid, None)

        if old_job is None:
            self._logger.warning("Задача %s уже не в расписании, не продлеваем", uid)
            return

        interval: float | int
        if not is_success and retry_delay_sec is not None:
            interval = retry_delay_sec
        else:
            interval = old_job.interval
        self._jobs[uid] = JobInfo(next_run=time.time() + interval, interval=old_job.interval)

    def seconds_until_next(self) -> float | None:
        """
        Считает минимальное время сна только по тем задачам, которые НЕ находятся в self._running.
        """
        earliest_run: float | int | None = None
        for uid, job in self._jobs.items():
            if uid in self._running:
                continue

            if earliest_run is None or earliest_run > job.next_run:
                earliest_run = job.next_run

        if earliest_run is None:
            return None

        return max(0.0, earliest_run - time.time())
