# apps/collector/actions/base.py
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from libs.collector.models import CollectResult
from libs.events.models import DeviceConfig
from libs.null_logger import NullLogger


class BaseCollectAction(ABC):
    """Абстрактный контракт для всех плагинов сбора данных."""

    def __init__(
        self,
        # TODO переделать на опциональный, в общем может ничего и не быть.
        #  И код будет проще (наверное)
        queue: asyncio.Queue[Any],
        *,
        logger: logging.Logger | None = None,
        **kwargs: Any,  # Сюда провалятся все уникальные креды (usr, psw и т.д.)
    ) -> None:
        self._queue = queue
        self._logger = logger or NullLogger(__name__)

        # Если дочернему классу передали что-то лишнее, чего он не ожидал,
        # мы сохраняем это, либо игнорируем, защищая от TypeError
        self._extra_params = kwargs

    @abstractmethod
    async def execute(self, device: DeviceConfig) -> CollectResult:
        """Метод выполнения сбора данных. Обязан быть реализован в каждом плагине."""
        ...
