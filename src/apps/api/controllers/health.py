# apps/api/controllers/health.py

from litestar import Controller, get


class HealthController(Controller):
    path = "/health"
    tags = ["Infrastructure"]

    @get("/startup")
    async def startup_check(self) -> dict[str, str]:
        """Указывает, что само ASGI-приложение запустилось."""
        return {"status": "started"}

    @get("/live")
    async def liveness_check(self) -> dict[str, str]:
        """Проверка, что Event Loop живой и реагирует на входящие вызовы."""
        return {"status": "alive"}
