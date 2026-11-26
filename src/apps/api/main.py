# apps/api/main.py
from litestar import Litestar, Response, get
from litestar.status_codes import HTTP_204_NO_CONTENT

from apps.api.controllers.health import HealthController
from apps.api.controllers.metrics import MetricsApiController


@get("/")
async def async_hello_world() -> dict[str, str]:
    return {"hello": "world"}


@get("/favicon.ico", include_in_schema=False)
async def disable_favicon() -> Response:
    return Response(
        content="",
        status_code=HTTP_204_NO_CONTENT,
        media_type="image/x-icon",
    )


def create_app() -> Litestar:

    return Litestar(
        route_handlers=[
            HealthController,
            MetricsApiController,
            async_hello_world,
            disable_favicon,
        ],
    )
