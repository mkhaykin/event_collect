import time
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceCreatedCommand:
    """Внутренняя команда на постановку устройства в расписание."""

    device_uid: str
    received_at: float = time.time()


@dataclass(frozen=True)
class DeviceDeletedCommand:
    """Внутренняя команда на постановку устройства в расписание."""

    device_uid: str
    received_at: float = time.time()


@dataclass(frozen=True)
class DeviceUpdatedCommand:
    """Внутренняя команда на постановку устройства в расписание."""

    device_uid: str
    received_at: float = time.time()
