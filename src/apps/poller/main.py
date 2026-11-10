# apps/poller/main.py
import asyncio
import logging
import sys

from apps.poller.service import PollerService
from libs.config import config

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,  # пока пусть не мусорит ...
    format="%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)


async def main() -> None:
    async with PollerService.factory(
        config.VALKEY_DSN,
        concurrency_limit=1000,
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
