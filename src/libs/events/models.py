# libs/events/config.py

from pydantic import BaseModel

from libs.models.config import BaseDeviceConfig, DeviceConfig


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
