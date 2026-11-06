# apps/collector/main.py
import asyncio
import logging
import sys
from typing import Any

from apps.collector.actions import DummyCollectAction
from apps.collector.engine import CollectorCoreEngine
from apps.collector.listener import CollectorBusListener
from apps.collector.registry import DeviceOnlineRegistry
from apps.collector.repository import CollectorDummyRepository
from apps.collector.scheduler import JobScheduler
from apps.device_provider.config import config

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)


VALKEY_URL = config.VALKEY_DSN


async def main() -> None:
    logger.info("запуск службы сбора данных Event Collector...")

    # событие для подъема основного потока из ожидания
    wakeup_event = asyncio.Event()
    # очередь от листера до основного потока
    internal_queue: asyncio.Queue[Any] = asyncio.Queue()

    # пока пустышка (потом PS)
    action_plugin = DummyCollectAction(logger=logger)
    # пока пустышка, потом сохранять инфу в БД
    db_repo = CollectorDummyRepository(logger=logger)

    registry = DeviceOnlineRegistry(logger=logger)

    # стартует задачи, контролирует расписание
    scheduler = JobScheduler(
        action=action_plugin,
        registry=registry,
        wakeup_event=wakeup_event,
        concurrency_limit=20,
        logger=logger,
    )

    # листенер, подписан на события поллера (online|offline)
    bus_listener = CollectorBusListener(
        valkey_url=VALKEY_URL,
        internal_queue=internal_queue,
        logger=logger,
    )
    await bus_listener.connect()

    # само ядро
    engine = CollectorCoreEngine(
        scheduler=scheduler,
        db_repo=db_repo,
        internal_queue=internal_queue,
        wakeup_event=wakeup_event,
        logger=logger,
    )

    # слушатель
    listener_task = asyncio.create_task(bus_listener.listen_forever())

    try:
        await engine.start_orchestration()
    except KeyboardInterrupt:
        logger.info("останавливаемся...")
    finally:
        listener_task.cancel()
        await engine.stop()
        await bus_listener.close()
        logger.info("bye")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
