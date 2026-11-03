import asyncio
import logging
import sys

import redis.asyncio as valkey

from apps.device_provider.config import config

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)


async def flush_valkey(valkey_dsn: str) -> None:
    logger.info("Начинаем очистку Valkey...")
    client = valkey.from_url(valkey_dsn, decode_responses=True)

    try:
        # конфигурации устройств
        device_keys = [key async for key in client.scan_iter("device:config:*")]
        # обновления
        heartbeat_keys = [key async for key in client.scan_iter("device:heartbeat:*")]

        keys_to_delete = device_keys + heartbeat_keys + ["devices:all"]

        result = await client.delete(*keys_to_delete)
        if result:
            logger.info(f"удалено ключей в Valkey: {result}")
        else:
            logger.info("нечего удалять")

    except Exception as e:
        logger.error(f"ошибка при очистке Valkey: {e}")
    finally:
        await client.aclose()


async def main() -> None:
    if "--force" not in sys.argv:
        confirm = input("подтверди очистку? (y/n): ")
        if confirm.lower() != "y":
            logger.info("отмена...")
            return

    await flush_valkey(config.VALKEY_DSN)
    logger.info("все очищено")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Процесс прерван.")
