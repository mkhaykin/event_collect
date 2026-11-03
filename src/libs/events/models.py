# libs/events/models.py
from typing import Literal, Optional

from pydantic import BaseModel


class BaseDeviceConfig(BaseModel):
    uid: str


class DeviceConfig(BaseDeviceConfig):
    ip: str
    check_type: Literal["icmp", "port"]
    port: Optional[int] = None
    check_interval_sec: int = 5
    collect_interval_min: int = 30
    rule_online_success: int = 3
    rule_offline_fails: int = 3


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
