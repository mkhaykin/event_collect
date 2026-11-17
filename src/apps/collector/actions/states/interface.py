# apps/collector/actions/states/interface.py
from typing import Optional, Protocol


class IStateStorage(Protocol):
    """Протокол для персистентного хранения текстовых слепков состояний (чекпоинтов) между опросами."""

    async def get_state(self, key: str) -> Optional[str]:
        """Возвращает сырую строку состояния по уникальному ключу задачи.

        Если состояние не найдено, возвращает None.
        """
        ...

    async def save_state(self, key: str, value: str) -> None:
        """Атомарно перезаписывает состояние для указанного ключа."""
        ...
