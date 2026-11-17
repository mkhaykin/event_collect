# apps/collector/actions/win_events/actions.py
import asyncio
import logging
import time
from typing import Any

from pydantic import ValidationError

from apps.collector.actions.base import BaseCollectAction
from apps.collector.actions.win_events.event_raw import EventRaw
from apps.collector.actions.win_events.helpers import (
    parse_json_stream,
    stream_powershell_output,
)
from apps.collector.actions.win_events.scripts import get_ps_script
from libs.collector.models import CollectResult
from libs.config import config
from libs.events.models import DeviceConfig


class WinEventsCollectAction(BaseCollectAction):
    """Отладочный плагин сбора данных."""

    def __init__(
        self,
        queue: asyncio.Queue[Any],
        *,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(queue, logger=logger, **kwargs)

        self._usr = self._extra_params.pop("usr")
        self._psw = self._extra_params.pop("psw")
        self._ps_script = self._extra_params.pop("ps_script", None) or get_ps_script()
        # TODO сделать варнинг если что-то осталось в self._extra_params

    async def execute(self, device: DeviceConfig) -> CollectResult:
        self._logger.debug("Начали опрашивать устройство: %s", device.uid)
        start_time = time.time()
        count = 0

        try:
            # port и server в параметры?
            raw_stream = stream_powershell_output(
                device.ip,
                5985,
                powershell_script=self._ps_script,
                username=self._usr,
                password=self._psw,
            )

            async for raw_dict in parse_json_stream(raw_stream):
                try:
                    raw_event = EventRaw.from_json(raw_dict)
                    await asyncio.wait_for(self._queue.put(raw_event), timeout=config.QUEUE_TIMEOUT)
                    count += 1
                except ValidationError:
                    self._logger.exception("Ошибка валидации строки для %s: %s", device.uid, raw_dict)
                except asyncio.QueueFull:
                    self._logger.exception("Не успеваем разгребать очередь, пропуск для %s", device.uid)

        except Exception as e:
            self._logger.exception("Критическая ошибка I/O стриминга WinRM для %s", device.uid)
            return CollectResult(device_uid=device.uid, is_success=False, error_message=str(e))

        exec_time = time.time() - start_time
        self._logger.info("Закончили опрашивать %s. Всего отправлено строк: %s", device.uid, count)

        return CollectResult(
            device_uid=device.uid,
            is_success=True,
            payload={"rows_count": count},
            execution_time_sec=exec_time,
        )
