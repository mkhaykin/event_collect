# apps/collector/win_events/actions.py
import logging
import time

from apps.collector.win_events.ch_buffer import ClickHouseWinEventBuffer
from apps.collector.win_events.event_raw import EventRaw
from apps.collector.win_events.helpers import (
    parse_json_stream,
    stream_powershell_output,
)
from libs.collector.models import CollectResult
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class WinEventsCollectAction:
    """Отладочный плагин сбора данных."""

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        port: int,
        usr: str,
        psw: str,
        *,
        ps_script: str,
        # queue: asyncio.Queue[EventFlat],
        ch_buffer: ClickHouseWinEventBuffer,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._host = host
        self._port = port
        self._usr = usr
        self._psw = psw

        self._ps_script = ps_script
        self._ch_buffer = ch_buffer

    async def execute(self, device: DeviceConfig) -> CollectResult:
        self._logger.debug("Начали опрашивать устройство: %s", device.uid)
        start_time = time.time()
        count = 0

        try:
            raw_stream = stream_powershell_output(
                self._host,
                self._port,
                powershell_script=self._ps_script,
                username=self._usr,
                password=self._psw,
            )

            async for raw_dict in parse_json_stream(raw_stream):
                try:
                    raw_event = EventRaw.from_json(raw_dict)
                    flat_event = raw_event.to_flat(collector_host="127.0.0.1", script_version="0.0.1")

                    await self._ch_buffer.add(flat_event)
                    count += 1
                except Exception as e:
                    self._logger.error("Ошибка парсинга отдельной строки для %s: %s", device.uid, e)

        except Exception as e:
            self._logger.exception("Критическая ошибка I/O стриминга WinRM для %s: %s", device.uid, e)
            return CollectResult(uid=device.uid, is_success=False, error_message=str(e))

        finally:
            # ИСПРАВЛЕНИЕ: Гарантированно выталкиваем остатки логов из ОЗУ в ClickHouse!
            # Теперь ни одна строчка журнала не останется висеть в памяти.
            await self._ch_buffer.flush()

        exec_time = time.time() - start_time
        self._logger.info("Закончили опрашивать %s. Всего успешно записано строк: %s", device.uid, count)

        return CollectResult(
            uid=device.uid,
            is_success=True,
            payload={"rows_count": count},
            execution_time_sec=exec_time,
        )
