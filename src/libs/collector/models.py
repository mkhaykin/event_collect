# libs/collector/models.py
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectResult:
    """Стандартизированная модель результатов сбора данных."""

    uid: str
    is_success: bool
    payload: dict[str, Any] | None = None
    execution_time_sec: float = 0.0
    error_message: str | None = None


@dataclass(frozen=True)
class DeviceOnlineCommand:
    """Внутренняя команда на постановку устройства в расписание."""

    uid: str
    received_at: float = time.time()


@dataclass(frozen=True)
class DeviceOfflineCommand:
    """Внутренняя command на удаление устройства из расписания."""

    uid: str
    received_at: float = time.time()


@dataclass(frozen=True)
class JobFinishedCommand:
    """Команда завершения выполнения задачи сбора для обновления JobScheduler."""

    uid: str
    is_success: bool
    result: CollectResult | None = None
