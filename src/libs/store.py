import logging
import time
from typing import Iterable, Literal

import clickhouse_connect
from clickhouse_connect.driver import AsyncClient

from libs.null_logger import NullLogger
from libs.poller.models import DeviceProbeResult


async def get_client() -> AsyncClient:
    # TODO в конфиг!
    client = await clickhouse_connect.get_async_client(
        dsn="clickhousedb://admin:your_secure_password@clickhouse:8123/my_database",
    )
    return client


class Store:
    def __init__(
        self,
        client: AsyncClient,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._client = client

    async def service_lifecycle_activity_store(
        self,
        service_name: str,
        event: Literal["started", "stopped"],
    ) -> None:
        self._logger.debug("Сохраняем: %s %s", service_name, event)

        await self._client.insert(
            "service_lifecycle",
            [
                (service_name, int(time.time() * 1000), event),
            ],
            column_names=["service_name", "timestamp", "event"],
        )

    async def store_probe_result(self, probes: Iterable[DeviceProbeResult]) -> None:
        rows = [
            (
                result.uid,
                result.timestamp,
                1 if result.is_success else 0,
                float(result.latency_ms),
                float(result.packet_loss),
                int(result.probes_sent),
                result.error_message or "",
            )
            for result in probes
        ]

        await self._client.insert(
            "device_probes",
            rows,
            column_names=[
                "uid",
                "timestamp",
                "is_success",
                "latency_ms",
                "packet_loss",
                "probes_sent",
                "error_message",
            ],
        )
