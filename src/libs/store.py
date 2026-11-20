import logging
import uuid
from typing import Iterable, Literal

import clickhouse_connect
from clickhouse_connect.driver import AsyncClient

from apps.collector.actions.win_events.event_flat import EventFlat
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
        session_id: uuid.UUID,
        timestamp: int,
        event: Literal["started", "stopped"],
    ) -> None:
        self._logger.debug("Сохраняем: %s %s", service_name, event)

        await self._client.insert(
            "service_lifecycle",
            [
                (service_name, session_id, timestamp, event),
            ],
            column_names=["service_name", "session_id", "timestamp", "event"],
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

    async def store_events(self, flat_events: list[EventFlat]) -> None:
        if not flat_events:
            return

        # Вытаскиваем массив плоских кортежей
        rows = [event.to_clickhouse_row() for event in flat_events]

        await self._client.insert(
            "device_events",
            rows,
            column_names=EventFlat.get_column_names(),
        )
