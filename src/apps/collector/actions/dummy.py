# apps/collector/actions/dummy.py
import asyncio
import logging
import time

from libs.collector.models import CollectResult
from libs.models.config import DeviceConfig
from libs.null_logger import NullLogger


class DummyCollectAction:
    """Отладочный плагин сбора данных."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

    async def execute(self, device: DeviceConfig) -> CollectResult:
        self._logger.debug("начали опрашивать %s", device.uid)
        start_time = time.time()

        # Имитируем тяжелый сетевой I/O запрос
        await asyncio.sleep(5)

        exec_time = time.time() - start_time
        self._logger.debug("закончили опрашивать %s, time=%s", device.uid, exec_time)

        return CollectResult(
            device_uid=device.uid,
            is_success=True,
            payload={"metrics_count": 42, "firmware": "v1.2.3"},
            execution_time_sec=exec_time,
        )
