# apps/poller/workers.py
import asyncio
import logging
from typing import Protocol

from libs.null_logger import NullLogger
from libs.poller.models import DeviceProbeResult


class NetworkChecker(Protocol):
    """Интерфейс для плагинов опроса (ICMP / TCP порт)."""

    async def probe(self, ip: str, port: int | None, count: int) -> tuple[bool, float, float]: ...


class DeviceNetworkWorker:
    """Изолированный исполнитель сетевой пробы."""

    def __init__(
        self,
        checker: NetworkChecker,
        result_queue: asyncio.Queue[DeviceProbeResult],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._checker = checker
        self._queue = result_queue

    async def run_probe(
        self,
        uid: str,
        ip: str,
        check_type: str,  # noqa: ARG002
        port: int | None,
        probes_count: int,
    ) -> None:
        """
        Изолированная задача опроса. Работает строго по входным параметрам.
        Перехватывает таймауты и ошибки, переводя их в легитимный fail-результат.
        """
        self._logger.debug("запускаем пробу для %s", uid)

        try:
            # TODO тут ставим лимит, потому как сейчас опрос 5 секунд.
            #  Подумать, это плохо, так как потом это период будет в конфиге.
            async with asyncio.timeout(4.0):
                is_ok, latency, loss = await self._checker.probe(ip, port, count=probes_count)

                result = DeviceProbeResult(
                    uid=uid,
                    is_success=is_ok,
                    latency_ms=latency,
                    packet_loss=loss,
                    probes_sent=probes_count,
                )
        except TimeoutError:
            self._logger.error("Timeout Error для %s", uid)
            result = DeviceProbeResult(
                uid=uid,
                is_success=False,
                packet_loss=100.0,
                probes_sent=probes_count,
                error_message="TimeoutError: Превышено ограничение в 4 секунды",
            )
        except Exception as e:
            self._logger.exception("An exception occurred %s", uid)
            result = DeviceProbeResult(
                uid=uid,
                is_success=False,
                packet_loss=100.0,
                probes_sent=probes_count,
                error_message=f"NetworkError: {str(e)}",
            )

        self._logger.debug("Результат пробы для %s: %s", uid, result)
        await self._queue.put(result)
