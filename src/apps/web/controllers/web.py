# src/apps/web/web.py
from litestar import Controller, get
from litestar.response import Template


class WebUiController(Controller):
    tags = ["Web UI Pages"]

    @get("/")
    async def overview_page(self) -> Template:
        return Template(template_name="overview.html")

    @get("/availability")
    async def availability_page(self) -> Template:
        return Template(template_name="empty.html", context={"title": "Доступность устройств"})

    @get("/collection")
    async def collection_page(self) -> Template:
        return Template(template_name="empty.html", context={"title": "Сбор данных"})

    @get("/events")
    async def events_page(self) -> Template:
        return Template(template_name="empty.html", context={"title": "События"})

    @get("/reports")
    async def reports_page(self) -> Template:
        return Template(template_name="empty.html", context={"title": "Отчеты"})

    @get("/notifications")
    async def notifications_page(self) -> Template:
        return Template(template_name="empty.html", context={"title": "Уведомления"})

    @get("/settings")
    async def settings_page(self) -> Template:
        return Template(template_name="empty.html", context={"title": "Настройки"})
