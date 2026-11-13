import logging
import time
from typing import Literal

import clickhouse_connect
from clickhouse_connect.driver import AsyncClient

from libs.null_logger import NullLogger


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
