# apps/poller/state_machine.py
import asyncio
import logging
from typing import Protocol

from libs.config import config
from libs.null_logger import NullLogger
from libs.poller.models import DeviceProbeResult, DeviceState


class StatusBusNotifier(Protocol):
    """Интерфейс отправки событий смены статуса в шину (Valkey)."""

    async def notify_online(self, uid: str) -> None: ...

    async def notify_offline(self, uid: str) -> None: ...


class DeviceStateMachine:
    """Управляет состоянием устройств. Слушает очередь результатов и
    отправляет изменение состояния в notifier"""

    FAIL_COUNT: int = config.POLLER_FAIL_COUNT
    SUCCESS_COUNT: int = config.POLLER_SUCCESS_COUNT

    def __init__(
        self,
        notifier: StatusBusNotifier,
        result_queue: asyncio.Queue[DeviceProbeResult],
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._notifier = notifier
        self._queue = result_queue
        self._states: dict[str, DeviceState] = {}

    def get_next_run_time(self, uid: str) -> float:
        """Возвращает timestamp планирования для Ticker."""
        if uid not in self._states:
            return 0.0  # Новые устройства запускаются мгновенно
        return self._states[uid].next_run_at

    def get_probes_config(self, uid: str) -> int:
        """Динамический расчет количества необходимых проб."""
        state = self._states.get(uid)
        if state and state.current_status == "online":
            return 3  # Для онлайн устройств делаем 3 пробы
        return 1  # Для офлайн — экономим сеть, делаем 1 пробу

    def calculate_next_schedule(self, uid: str, current_time: float, interval_sec: int) -> None:
        """
        Динамический сдвиг сетки времени на основе взаимно простых чисел.
        Если устройство офлайн — увеличиваем интервал в два раза (для примера).
        """
        if uid not in self._states:
            self._states[uid] = DeviceState(uid=uid)

        state = self._states[uid]
        interval = interval_sec if state.current_status == "online" else (interval_sec * 2)
        state.next_run_at = current_time + interval

    async def start_processing(self) -> None:
        """Фоновый бесконечный цикл обработки очереди результатов."""
        self._logger.debug("Start Processing")
        while True:
            result = await self._queue.get()
            await self._process_single_result(result)
            self._queue.task_done()

    async def _process_single_result(self, result: DeviceProbeResult) -> None:
        uid = result.uid
        if uid not in self._states:
            self._states[uid] = DeviceState(uid=uid)

        state = self._states[uid]

        if result.is_success:
            state.success_streak += 1
            state.fail_streak = 0

            # Логика перехода в Online
            if state.current_status != "online" and state.success_streak >= self.SUCCESS_COUNT:
                state.current_status = "online"
                await self._notifier.notify_online(uid)
        else:
            state.fail_streak += 1
            state.success_streak = 0

            # Логика перехода в Offline
            if state.current_status != "offline" and state.fail_streak >= self.FAIL_COUNT:
                state.current_status = "offline"
                await self._notifier.notify_offline(uid)
