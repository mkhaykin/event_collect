# libs/poller/config.py
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel


@dataclass(frozen=True)
class DeviceProbeResult:
    """Объект результата опроса, генерируемый воркером."""

    uid: str
    is_success: bool
    latency_ms: float = 0.0
    packet_loss: float = 0.0
    probes_sent: int = 1
    timestamp: float = field(default_factory=lambda: int(time.time() * 1000))
    error_message: Optional[str] = None


class DeviceState(BaseModel):
    """Внутреннее состояние счетчиков устройства мониторинга."""

    uid: str
    current_status: Literal["unknown", "online", "offline"] = "unknown"
    success_streak: int = 0
    fail_streak: int = 0
    next_run_at: float = 0.0  # Unix timestamp следующего запуска


class DeviceOnlineEvent(BaseModel):
    uid: str
    status: Literal["online", "offline"] = "online"


class DeviceOfflineEvent(BaseModel):
    uid: str
    status: Literal["online", "offline"] = "online"
