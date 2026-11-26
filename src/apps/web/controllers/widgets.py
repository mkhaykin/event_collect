# src/apps/web_ui/widgets.py
import httpx
from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import ServiceUnavailableException
from litestar.response import Template

from libs.models.availability import (
    AvailabilityWidgetContext,
    BackendAvailabilityResponse,
)


class BackendMetricsClient:
    def __init__(self, base_url: str = "http://api:8000/api/v1/metrics") -> None:
        self._base_url = base_url

    async def get_availability(self, period: str, date: str) -> BackendAvailabilityResponse:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=3.0) as client:
            try:
                response = await client.get(
                    "/availability",
                    params={"global_period": period, "global_date": date},
                )
                response.raise_for_status()

                return BackendAvailabilityResponse.model_validate(response.json())

            except (httpx.HTTPError, httpx.TimeoutException) as e:
                raise ServiceUnavailableException(
                    detail="Внутренний сервис метрик временно недоступен.",
                ) from e


class WebUiWidgetsController(Controller):
    path = "/components"
    tags = ["Web UI HTMX Components"]

    dependencies = {"metrics_client": Provide(BackendMetricsClient)}

    @get("/availability")
    async def get_availability_widget(
        self,
        metrics_client: BackendMetricsClient,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
    ) -> Template:
        dto: BackendAvailabilityResponse = await metrics_client.get_availability(
            period=global_period,
            date=global_date,
        )
        view_context = AvailabilityWidgetContext(
            online_count=dto.online_count,
            offline_count=dto.offline_count,
        )

        return Template(template_name="widgets/device_availability.html", context=view_context.model_dump())

    @get("/response-quality")
    async def get_response_quality_widget(
        self,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
    ) -> Template:
        mock_context = {
            "avg_ping_ms": 12,
            "drop_pct": 8,
        }
        return Template(template_name="widgets/response_quality.html", context=mock_context)

    @get("/collection-summary")
    async def get_collection_summary_widget(
        self,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
    ) -> Template:
        mock_context = {
            "total_gb": 48.7,
            "speed_pct": 12,
        }
        return Template(template_name="widgets/data_collection.html", context=mock_context)

    @get("/device-table")
    async def get_device_table_component(
        self,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
    ) -> Template:
        """СТРОКА 2: Рендерит расширенную таблицу хостов."""
        mock_devices = [
            {
                "uid": "PC-201",
                "ip": "192.168.1.50",
                "ping": "4 мс",
                "uptime": "14д 5ч",
                "last_check": "10:28:15",
                "status": "ONLINE",
                "status_color": "emerald",
            },
            {
                "uid": "SRV-DB-01",
                "ip": "10.0.4.12",
                "ping": "1 мс",
                "uptime": "128д 2ч",
                "last_check": "10:29:01",
                "status": "ONLINE",
                "status_color": "emerald",
            },
            {
                "uid": "PC-205",
                "ip": "192.168.1.55",
                "ping": "—",
                "uptime": "—",
                "last_check": "09:15:32",
                "status": "OFFLINE",
                "status_color": "rose",
            },
            {
                "uid": "ROUTER-GW",
                "ip": "192.168.1.1",
                "ping": "2 мс",
                "uptime": "342д 11ч",
                "last_check": "10:28:59",
                "status": "ONLINE",
                "status_color": "emerald",
            },
        ]
        return Template(template_name="widgets/device_table.html", context={"devices": mock_devices})

    @get("/collection-details")
    async def get_collection_details_component(
        self,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
        tab: str = "periods",  # Варианты: periods, sources, types
    ) -> Template:
        """СТРОКА 2: Детализация объема сбора логов с динамическими табами."""
        if tab == "sources":
            # Вариант Б: По источникам (Круговая диаграмма)
            mock_data = [45.2, 30.1, 15.4, 9.3]  # % распределения по серверам
            return Template(
                template_name="widgets/collection_details_sources.html",
                context={"chart_data": mock_data, "active_tab": "sources"},
            )

        elif tab == "types":
            # Вариант В: По типам (Столбчатая диаграмма)
            mock_data = [120, 85, 45, 10]  # Количество тысяч событий
            return Template(
                template_name="widgets/collection_details_types.html",
                context={"chart_data": mock_data, "active_tab": "types"},
            )

        # Вариант А (Дефолт): По периодам (Линейный график)
        mock_data = [12.4, 15.1, 11.2, 18.4, 22.1, 14.8, 19.3]
        return Template(
            template_name="widgets/collection_details_periods.html",
            context={"chart_data": mock_data, "active_tab": "periods"},
        )

    @get("/events-categories")
    async def get_events_categories_component(
        self,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
    ) -> Template:
        """СТРОКА 3: Детальное соотношение логов Windows по категориям."""

        # Данные строго по твоему макету
        mock_categories = [
            {"label": "Критичные", "count": 218, "pct": 17.5, "color": "#ef4444"},  # Красный (rose-500)
            {"label": "Ошибки", "count": 386, "pct": 30.9, "color": "#f97316"},  # Оранжевый (orange-500)
            {"label": "Предупреждения", "count": 312, "pct": 25.0, "color": "#eab308"},  # Желтый (amber-500)
            {"label": "Информация", "count": 332, "pct": 26.6, "color": "#3b82f6"},  # Синий (blue-500)
        ]

        return Template(
            template_name="widgets/events_categories.html",
            context={
                "total_count": "1 248",
                "categories": mock_categories,
            },
        )

    @get("/recent-events")
    async def get_recent_events_component(
        self,
        global_period: str = "1d",  # noqa: ARG002
        global_date: str = "",  # noqa: ARG002
    ) -> Template:
        """СТРОКА 3: Рендерит ленту последних системных алертов."""
        mock_events = [
            {
                "time": "10:28",
                "level": "Критично",
                "badge_color": "rose",
                "msg": "Устройство PC-205 перешло в статус OFFLINE",
            },
            {
                "time": "10:15",
                "level": "Ошибка",
                "badge_color": "amber",
                "msg": "SRV-DB-01: Обнаружен брутфорс! 5000 отказов входа (ID 4625)",
            },
            {
                "time": "09:42",
                "level": "Предупреждение",
                "badge_color": "sky",
                "msg": "PC-201: Обогащение чекпоинта восстановлено из ClickHouse",
            },
        ]
        return Template(template_name="widgets/recent_events.html", context={"events": mock_events})
