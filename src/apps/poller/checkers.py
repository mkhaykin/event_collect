# apps/poller/checkers.py
import asyncio
import logging
import random
from typing import NamedTuple, Protocol

from icmplib import async_ping

from libs.null_logger import NullLogger


class ProbeMetrics(NamedTuple):
    is_success: bool
    latency_ms: float
    packet_loss: float


class NetworkChecker(Protocol):
    """Протокол для сетевых плагинов (ICMP, TCP, etc.)."""

    async def probe(self, ip: str, port: int | None, count: int) -> ProbeMetrics:
        """Атомарная проба сетевой доступности устройства."""
        ...


class IcmpChecker:
    """Реальный плагин для асинхронной проверки доступности устройств по ICMP (Пинг)."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

    async def probe(self, ip: str, port: int | None, count: int) -> ProbeMetrics:  # noqa: ARG002
        """
        Выполняет серию асинхронных пингов до указанного IP.
        Параметр 'port' для ICMP игнорируется.
        """
        try:
            # Вызываем асинхронный пинг из icmplib
            # timeout=1.0 означает максимальное ожидание одного ответа в секундах
            host = await async_ping(address=ip, count=count, timeout=1.0)

            # Устройство доступно, если вернулся хотя бы один пакет (пакетные потери < 100%)
            is_success = host.is_alive

            return ProbeMetrics(
                is_success=is_success,
                latency_ms=host.avg_rtt if is_success else 0.0,
                packet_loss=host.packet_loss * 100.0,  # Переводим коэф. в проценты (0.0 - 100.0)
            )

        except Exception:
            self._logger.exception("Критическая системная ошибка ICMP для %s:", ip)
            return ProbeMetrics(
                is_success=False,
                latency_ms=0.0,
                packet_loss=100.0,
            )


class DummyNetworkChecker:
    """Асинхронный плагин сетевых проверок для отладки."""

    async def probe(
        self,
        ip: str,  # noqa: ARG002
        port: int | None,  # noqa: ARG002
        count: int,  # noqa: ARG002
    ) -> ProbeMetrics:
        # симулируем сетевую задержку IO-bound операции
        await asyncio.sleep(0.2)

        # рандомный генератор сбоев для теста State Machine (90% успех)
        is_success = random.random() > 0.1  # # noqa: S311 PLR2004
        latency = random.uniform(5.0, 45.0) if is_success else 0.0  # noqa: S311
        loss = 0.0 if is_success else 100.0

        return ProbeMetrics(is_success=is_success, latency_ms=latency, packet_loss=loss)
