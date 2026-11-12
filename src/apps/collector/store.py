# apps/collector/store.py

import logging

from libs.null_logger import NullLogger


class CollectorStatusStore:
    """репозиторий истории состояний в Postgres (заглушка)."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or NullLogger(__name__)

    async def log_status_change(self, uid: str, status: str) -> None:
        self._logger.info(f"[БД Лог] Зафиксировано переключение {uid} -> {status}")
