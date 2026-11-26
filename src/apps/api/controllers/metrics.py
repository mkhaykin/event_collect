# src/apps/api/controllers/metrics.py
from typing import Literal

from litestar import Controller, get

from libs.models.availability import BackendAvailabilityResponse


class MetricsApiController(Controller):
    path = "/api/v1/metrics"
    tags = ["Backend JSON Metrics API"]

    @get("/availability")
    async def get_availability_data(
        self,
        global_period: Literal["1h", "1d", "1w", "1m"] = "1h",
        global_date: str = "",  # noqa: ARG002
    ) -> BackendAvailabilityResponse:
        """Возвращает сырой JSON-срез состояния пула устройств."""
        return BackendAvailabilityResponse(
            online_count=622 if global_period == "1h" else 700,
            offline_count=22,
        )
