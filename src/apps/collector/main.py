# apps/collector/main.py
import asyncio
import logging
import signal
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
        main_task = asyncio.create_task(service.start_loop())

        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGTERM, main_task.cancel)
            loop.add_signal_handler(signal.SIGINT, main_task.cancel)
        except NotImplementedError:
            pass

        try:
            await main_task
        except KeyboardInterrupt:
            logger.info("Остановка сервиса ...")
        finally:
            logger.info("bye...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
