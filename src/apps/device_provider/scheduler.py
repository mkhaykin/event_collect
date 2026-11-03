# apps/device_provider/scheduler.py
import logging

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from apps.device_provider.tasks import broker

logger = logging.getLogger("DeviceProvider")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(module)s:%(lineno)d] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# Создаем шедулер, который сам найдет все cron-правила в декораторах тасок
scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)
