# apps/poller/checkers.py
import asyncio
import random


class DummyNetworkChecker:
    """Асинхронный плагин сетевых проверок для отладки."""

    async def probe(
        self,
        ip: str,  # noqa: ARG002
        port: int | None,  # noqa: ARG002
        count: int,  # noqa: ARG002
    ) -> tuple[bool, float, float]:
        # симулируем сетевую задержку IO-bound операции
        await asyncio.sleep(0.2)

        # рандомный генератор сбоев для теста State Machine (90% успех)
        is_success = random.random() > 0.1  # # noqa: S311 PLR2004
        latency = random.uniform(5.0, 45.0) if is_success else 0.0  # noqa: S311
        loss = 0.0 if is_success else 100.0

        return is_success, latency, loss
