# libs/events/models.py
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseDeviceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str


# TODO добавить name, но если остутствует, что использовать uid
class CollectorTaskConfig(BaseModel):
    uid: str
    type: Literal["win_events",]
    interval_min: int = 30  # TODO в секунды наверное? чтобы единообразно
    params: dict[str, Any]  # Уникальные usr, psw, ps_script, community, oids


# TODO разнести модели! DeviceConfig - это чисто девайс, без вложенных коллекторов.
#  со вложенными коллекторами - это уже конфиг.
class DeviceConfig(BaseDeviceConfig):
    ip: str
    check_type: Literal["icmp", "port"]
    port: Optional[int] = None
    check_interval_sec: int = 5
    rule_online_success: int = 3
    rule_offline_fails: int = 3

    collectors: list[CollectorTaskConfig] = Field(default_factory=list)


class DeviceHeartbeat(BaseDeviceConfig):
    created_at: str
    updated_at: str


class DeviceCreatedEvent(BaseDeviceConfig):
    device: DeviceConfig | None = None


class DeviceUpdatedEvent(BaseDeviceConfig):
    device: DeviceConfig | None = None
    device_old: DeviceConfig | None = None


class DeviceDeletedEvent(BaseModel):
    uid: str
