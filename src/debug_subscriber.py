import asyncio
import logging

import redis.asyncio as valkey

from libs.config import config

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")
logger = logging.getLogger("EventChecker")


async def check_events(valkey_dsn: str) -> None:
    client = valkey.from_url(valkey_dsn, decode_responses=True)

    async with client.pubsub() as pubsub:
        await pubsub.psubscribe("events:device_*")
        logger.info("подключились, слушаем каналы 'events:device_*'...")

        try:
            async for message in pubsub.listen():
                # пропускаем служебных сообщений
                if message["type"] not in ("message", "pmessage"):
                    continue

                channel = message["channel"]
                data = message["data"]

                logger.info(f"получено событие из канала [{channel}]:")
                logger.info(f"{data}")
        except asyncio.CancelledError:
            logger.info("подписка отменена.")
        finally:
            await pubsub.punsubscribe("events:device_*")


if __name__ == "__main__":
    try:
        asyncio.run(check_events(config.VALKEY_DSN))
    except KeyboardInterrupt:
        logger.info("выход...")
