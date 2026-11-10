# apps/collector/main.py
import asyncio
import logging
import sys

from apps.collector.service import CollectorService
from libs.config import config

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)


VALKEY_URL = config.VALKEY_DSN


async def main() -> None:
    async with CollectorService.factory(
        config.VALKEY_DSN,
        logger=logger,
    ) as service:
        try:
            await service.start_loop()
        except KeyboardInterrupt:
            logger.info("Остановка сервиса ...")
        finally:
            logger.info("bye...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
