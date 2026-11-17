# apps/collector/states/file_storage.py
# Пример реализации интерфейса на локальных файлах, проблема в сохранении данных
# при остановке, но для проверки пойдет
import logging
import os

import aiofiles  # pip install aiofiles для неблокирующего дискового I/O

from libs.null_logger import NullLogger


class FileStateStorage:
    def __init__(
        self,
        base_dir: str = "./storage/checkpoints",
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _get_path(self, key: str) -> str:
        # Превращаем ключ "checkpoint:web-server-03:win_events" в безопасное имя файла
        safe_filename = key.replace(":", "__") + ".json"
        return os.path.join(self._base_dir, safe_filename)

    async def get_state(self, key: str) -> str | None:
        self._logger.debug("Getting checkpoint for %s", key)
        path = self._get_path(key)
        if not os.path.exists(path):
            return None
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            text = await f.read()
            self._logger.debug("Received checkpoint for %s: %s", key, text)
        return text  # type: ignore[no-any-return]

    async def save_state(self, key: str, value: str) -> None:
        self._logger.debug("Save checkpoint for %s: %s", key, value)
        path = self._get_path(key)
        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(value)
