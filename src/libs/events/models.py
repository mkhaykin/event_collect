# libs/events/models.py

from pydantic import BaseModel, ConfigDict

from libs.models.config import DeviceConfig


class DeviceCreatedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str
    device: DeviceConfig | None = None


class DeviceUpdatedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str
    device: DeviceConfig | None = None
    device_old: DeviceConfig | None = None


class DeviceDeletedEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    uid: str
