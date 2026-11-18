from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# TODO добавить name, но если остутствует, что использовать uid
class BaseDeviceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str


# TODO разнести модели! DeviceConfig - это чисто девайс, без вложенных коллекторов.
#  со вложенными коллекторами - это уже конфиг.
class CollectorTaskConfig(BaseModel):
    uid: str
    type: Literal["win_events",]
    interval_min: int = 30  # TODO в секунды наверное? чтобы единообразно
    params: dict[str, Any]  # Уникальные usr, psw, ps_script, community, oids


class DeviceConfig(BaseDeviceConfig):
    ip: str
    check_type: Literal["icmp", "port"]
    port: Optional[int] = None
    check_interval_sec: int = 5
    rule_online_success: int = 3
    rule_offline_fails: int = 3

    collectors: list[CollectorTaskConfig] = Field(default_factory=list)
