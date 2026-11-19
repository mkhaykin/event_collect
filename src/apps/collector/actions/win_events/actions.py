# apps/collector/actions/win_events/actions.py
import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from apps.collector.actions.base import BaseCollectAction
from apps.collector.actions.states.interface import IStateStorage
from apps.collector.actions.win_events.event_raw import EventRaw
from apps.collector.actions.win_events.helpers import (
    parse_json_stream,
    stream_powershell_output,
)
from apps.collector.actions.win_events.scripts import get_ps_script
from libs.collector.models import CollectResult
from libs.config import config
from libs.models.task import TaskDescription


class WinEventsCheckpoint(BaseModel):
    """Слепок состояния инкрементального сбора журналов Windows."""

    # XML-строка закладки WinRM EventLogBookmark. None означает "первый холодный старт"
    "bookmark_xml: str | None = None"  # TODO пока не используется

    # Системные маркеры для отладки и мониторинга здоровья самого коллектора
    last_collected_record_id: int | None = None
    updated_at: float = time.time()


class WinEventsCollectAction(BaseCollectAction):
    """Отладочный плагин сбора данных."""

    def __init__(
        self,
        queue: asyncio.Queue[Any],
        state_storage: IStateStorage | None = None,
        *,
        logger: logging.Logger | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(queue, state_storage, logger=logger, **kwargs)

        self._usr = self._extra_params.pop("usr")
        self._psw = self._extra_params.pop("psw")
        # TODO вот тут переделываем, не вариант так ...
        self._ps_script = self._extra_params.pop("ps_script", None) or get_ps_script()
        # TODO сделать варнинг если что-то осталось в self._extra_params

    # TODO не DeviceConfig, а спец моделька типа TaskParams, где будет
    #  все что надо в плоском виде. И тогда можно будет разгрузить
    #  конструктор на _extra_params!
    async def execute(self, task: TaskDescription) -> CollectResult:
        self._logger.debug("Начали выполнять задачу: %s", task.uid)
        start_time = time.time()
        count = 0
        last_rec_id: int = -1

        # TODO вот это в отдельную функцию вынести
        if self._state_storage is not None:
            text = await self._state_storage.get_state(
                key=task.uid,
            )
            if text is not None:
                try:
                    value = WinEventsCheckpoint.model_validate_json(text)
                    last_rec_id = value.last_collected_record_id or -1
                    self._logger.warning("Вытащили последний id=%s", last_rec_id)
                except ValidationError:
                    self._logger.warning("Не смог разобрать модель из чекпоинта %s", text)
                    last_rec_id = -1
                else:
                    self._ps_script = get_ps_script(last_record_id=last_rec_id)

        try:
            # port и server в параметры?
            raw_stream = stream_powershell_output(
                task.host_ip,
                5985,  # TODO не должно быть тут!
                powershell_script=self._ps_script,
                username=self._usr,
                password=self._psw,
            )

            async for raw_dict in parse_json_stream(raw_stream):
                try:
                    raw_event = EventRaw.from_json(raw_dict)
                    await asyncio.wait_for(self._queue.put(raw_event), timeout=config.QUEUE_TIMEOUT)
                    last_rec_id = max(last_rec_id, int(raw_event.system.event_record_id or -1))
                    count += 1
                except ValidationError:
                    self._logger.exception("Ошибка валидации строки для %s: %s", task.uid, raw_dict)
                except asyncio.QueueFull:
                    self._logger.exception("Не успеваем разгребать очередь, пропуск для %s", task.uid)

        except Exception as e:
            self._logger.exception("Критическая ошибка I/O стриминга WinRM для %s", task.uid)
            return CollectResult(device_uid=task.uid, is_success=False, error_message=str(e))

        exec_time = time.time() - start_time
        self._logger.info(
            "Закончили опрашивать %s. Всего отправлено строк: %s. Время выполнения: %s",
            task.uid,
            count,
            exec_time,
        )

        if self._state_storage is not None and last_rec_id != -1:
            await self._state_storage.save_state(
                key=task.uid,
                value=WinEventsCheckpoint(
                    last_collected_record_id=last_rec_id,
                ).model_dump_json(),
            )

        return CollectResult(
            device_uid=task.uid,
            is_success=True,
            payload={"rows_count": count},
            execution_time_sec=exec_time,
        )
