# apps/api/main.py
from pathlib import Path

from litestar import Litestar, Response, get
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.static_files import StaticFilesConfig
from litestar.status_codes import HTTP_204_NO_CONTENT
from litestar.template import TemplateConfig

from apps.web.controllers.web import WebUiController
from apps.web.controllers.widgets import WebUiWidgetsController

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


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
            WebUiController,
            WebUiWidgetsController,
            disable_favicon,
        ],
        template_config=TemplateConfig(
            directory=TEMPLATES_DIR,
            engine=JinjaTemplateEngine,
        ),
        static_files_config=[
            StaticFilesConfig(
                directories=[STATIC_DIR],
                path="/static",
                name="static",
            ),
        ],
    )
