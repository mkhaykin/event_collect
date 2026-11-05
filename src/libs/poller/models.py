# libs/poller/models.py
from typing import Literal, Optional

from pydantic import BaseModel


class DeviceProbeResult(BaseModel):
    """Объект результата опроса, генерируемый воркером."""

    uid: str
    is_success: bool
    latency_ms: float = 0.0
    packet_loss: float = 0.0
    probes_sent: int = 1
    error_message: Optional[str] = None


class DeviceState(BaseModel):
    """Внутреннее состояние счетчиков устройства мониторинга."""

    uid: str
    current_status: Literal["unknown", "online", "offline"] = "unknown"
    success_streak: int = 0
    fail_streak: int = 0
    next_run_at: float = 0.0  # Unix timestamp следующего запуска
