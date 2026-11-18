from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from libs.models.task import TaskDescription
from libs.models.types import CheckType, TaskParamsType, TaskType


# TODO добавить name, но если остутствует, что использовать uid
class BaseDeviceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str


# TODO разнести модели! DeviceConfig - это чисто девайс, без вложенных коллекторов.
#  со вложенными коллекторами - это уже конфиг.
class CollectorTaskConfig(BaseModel):
    uid: str
    type: TaskType
    interval_min: int = 30  # TODO в секунды наверное? чтобы единообразно
    params: TaskParamsType


class DeviceConfig(BaseDeviceConfig):
    ip: str
    port: Optional[int] = None  # TODO потом удалить
    # TODO переделать структуру, надо выделять отдельную модель Checker
    check_type: CheckType
    check_interval_sec: int = 5

    rule_online_success: int = 3
    rule_offline_fails: int = 3

    collectors: list[CollectorTaskConfig] = Field(default_factory=list)

    def get_collectors(self) -> tuple[TaskDescription, ...]:
        return tuple(
            TaskDescription(
                uid=f"{self.uid}:{item.uid}",
                device_uid=self.uid,
                host_name=self.ip,  # TODO добавить в модельку
                host_ip=self.ip,
                task_uid=item.uid,
                type=item.type,
                interval_sec=item.interval_min * 60,
                params=item.params.copy(),
            )
            for item in self.collectors
        )
