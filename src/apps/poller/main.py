# apps/poller/main.py
import asyncio
import logging
import sys

from apps.device_provider.config import config
from apps.poller.bus_notifier import StatusBusNotifier
from apps.poller.checkers import DummyNetworkChecker
from apps.poller.listener import PollerBusListener
from apps.poller.registry import DeviceRegistry
from apps.poller.repository import PollerValkeyRepository
from apps.poller.state_machine import DeviceStateMachine
from apps.poller.ticker import PollerTickerService
from apps.poller.workers import DeviceNetworkWorker
from libs.poller.models import DeviceProbeResult

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def main() -> None:
    repo = PollerValkeyRepository(config.VALKEY_DSN)
    await repo.connect()

    bus_notifier = StatusBusNotifier(config.VALKEY_DSN)
    await bus_notifier.connect()

    # реестр устройств
    registry = DeviceRegistry()
    result_queue: asyncio.Queue[DeviceProbeResult] = asyncio.Queue()

    # загрузка текущих конфигураций из ValKey при старте (вынести куда-нить) ....
    logger.info("загрузка устройств из ValKey...")
    initial_devices = await repo.load_all_active_configs()
    for dev in initial_devices:
        await registry.add_or_update(dev)
    logger.info("найдено устройств: %s", len(initial_devices))
    await repo.close()  # Стартовый репозиторий больше не нужен, закрываемся

    bus_listener = PollerBusListener(config.VALKEY_DSN, registry)
    await bus_listener.connect()

    # пока поддельная опрашивалка
    checker = DummyNetworkChecker()
    # пул воркеров
    worker_pool = DeviceNetworkWorker(checker=checker, result_queue=result_queue, logger=logger)
    # хранение состояний
    state_machine = DeviceStateMachine(notifier=bus_notifier, result_queue=result_queue, logger=logger)

    ticker_service = PollerTickerService(
        registry=registry,
        state_machine=state_machine,
        worker_pool=worker_pool,
        concurrency_limit=1000,
        logger=logger,
    )

    # запускаем хранение состояний
    sm_task = asyncio.create_task(state_machine.start_processing())
    # тут поток слушателя от device provider-а
    listener_task = asyncio.create_task(bus_listener.listen_forever())

    try:
        # собственно основной цикл
        await ticker_service.start_loop()
    except KeyboardInterrupt:
        logger.info("Остановка сервиса ...")
    finally:
        sm_task.cancel()
        listener_task.cancel()

        await bus_listener.close()
        await bus_notifier.close()
        logger.info("bye...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
