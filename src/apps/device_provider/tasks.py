# apps/device_provider/tasks.py
import logging
from typing import Annotated, AsyncGenerator

from taskiq import TaskiqDepends
from taskiq_redis import ListQueueBroker

from apps.device_provider.config import config
from apps.device_provider.service import DeviceProviderService

broker = ListQueueBroker(
    config.VALKEY_DSN,
    socket_timeout=None,
    socket_connect_timeout=10,
    socket_keepalive=True,
)


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def get_provider_service() -> AsyncGenerator[DeviceProviderService, None]:
    path = "/storage/devices.yaml"
    service = DeviceProviderService.factory(path, config.VALKEY_DSN, logger=logger)
    await service.connect()
    try:
        yield service
    finally:
        await service.close()


DeviceProviderDep = Annotated[DeviceProviderService, TaskiqDepends(get_provider_service)]


@broker.task(
    name="provider:sync_configuration",
    schedule=[{"cron": "*/1 * * * *"}],
)
async def run_sync_task(service: DeviceProviderDep) -> None:
    await service.sync_configuration()
