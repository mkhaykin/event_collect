from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from libs.models.task import TaskDescription
from libs.models.types import CheckType, TaskParamsType, TaskType


class BaseConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str
    name: str = ""

    @model_validator(mode="before")
    @classmethod
    def set_default_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "uid" not in data or data["uid"] is None:
                data["uid"] = data["name"]

            if "name" not in data or data["name"] is None:
                data["name"] = data["uid"]

        return data

    def __str__(self) -> str:
        return self.name or self.uid


class CollectorConfig(BaseConfig):
    model_config = ConfigDict(frozen=True)

    type: TaskType
    interval_min: int = 30  # TODO в секунды наверное? чтобы единообразно
    params: TaskParamsType


class DeviceConfig(BaseConfig):
    model_config = ConfigDict(frozen=True)

    ip: str
    port: Optional[int] = None  # TODO потом удалить
    # TODO переделать структуру, надо выделять отдельную модель Checker
    check_type: CheckType
    check_interval_sec: int = 5

    rule_online_success: int = 3
    rule_offline_fails: int = 3

    collectors: list[CollectorConfig] = Field(default_factory=list)

    def get_collectors(self) -> tuple[TaskDescription, ...]:
        return tuple(
            TaskDescription(
                uid=f"{self.uid}:{item.uid}",
                device_uid=self.uid,
                device_name=self.name,
                host_name=self.ip,  # TODO пока пустышка
                host_ip=self.ip,
                task_uid=item.uid,
                task_name=item.name,
                type=item.type,
                interval_sec=item.interval_min * 60,
                params=item.params.copy(),
            )
            for item in self.collectors
        )
