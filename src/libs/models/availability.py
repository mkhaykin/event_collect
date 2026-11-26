from pydantic import BaseModel, computed_field


class BackendAvailabilityResponse(BaseModel):
    """Количество устройств онлайн и оффлайн. Это то, что возвращает api"""

    online_count: int
    offline_count: int


class AvailabilityWidgetContext(BaseModel):
    """Количество устройств онлайн и оффлайн. Это для верстки страницы (jinja)"""

    online_count: int
    offline_count: int

    @property
    def _devices(self) -> int:
        return self.online_count + self.offline_count

    @computed_field
    def total_devices(self) -> int:
        return self.online_count + self.offline_count

    @computed_field
    def online_pct(self) -> str:
        return str(round(100 * self.online_count / self._devices, 2))

    @computed_field
    def offline_pct(self) -> str:
        return str(round(100 * self.offline_count / self._devices, 2))

    @computed_field
    def has_offline_alerts(self) -> bool:
        return self.offline_count > 0
