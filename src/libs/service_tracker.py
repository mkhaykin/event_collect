# apps/common/lifecycle.py
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal, Protocol

from libs.null_logger import NullLogger


class IServiceStore(Protocol):
    async def service_lifecycle_activity_store(
        self,
        service_name: str,
        session_id: uuid.UUID,
        event: Literal["started", "stopped"],
    ) -> None:
        pass


class ServiceLifecycleTracker:
    def __init__(
        self,
        store: IServiceStore,
        service_name: str,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._store = store
        self._name = service_name

        self._session_id = uuid.uuid4()

    @asynccontextmanager
    async def track(self) -> AsyncGenerator[None, None]:
        """фиксируем старт и финиш сервиса"""
        self._logger.info(
            "Регистрация запуска сервиса '%s' (%s)...",
            self._name,
            self._session_id,
        )
        try:
            await self._store.service_lifecycle_activity_store(
                self._name,
                self._session_id,
                "started",
            )
        except Exception:
            self._logger.exception("Не удалось записать метрику старта '%s' в ClickHouse", self._name)

        try:
            yield
        finally:
            self._logger.info(
                "Регистрация остановки сервиса '%s' (%s)...",
                self._name,
                self._session_id,
            )
            try:
                await self._store.service_lifecycle_activity_store(
                    self._name,
                    self._session_id,
                    "stopped",
                )
            except Exception:
                self._logger.exception("Не удалось записать метрику остановки '%s' в ClickHouse", self._name)
