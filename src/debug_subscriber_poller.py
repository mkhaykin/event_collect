# apps/debug_subscriber_poller.py
import asyncio
import logging

import redis.asyncio as valkey

from apps.poller.bus_notifier import StatusBusNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(name)s] - %(message)s")
logger = logging.getLogger("BusSubscriber")

VALKEY_URL = "redis://localhost:6379/0"


async def start_debug_subscriber() -> None:
    client = valkey.from_url(VALKEY_URL, decode_responses=True)

    async with client.pubsub() as pubsub:
        # подписываемся на оба канала нотификатора
        channels = [
            StatusBusNotifier.CONFIG_EVENT_ONLINE,
            StatusBusNotifier.CONFIG_EVENT_OFFLINE,
        ]
        await pubsub.subscribe(*channels)
        logger.info("слушаем: %s. Ожидаем эвенты...", channels)

        try:
            async for message in pubsub.listen():
                if message["type"] not in ("message", "pmessage"):
                    continue

                channel = message["channel"]
                payload = message["data"]

                logger.info("смена статуса на шине [%s] -> Данные: %s", channel, payload)
        except asyncio.CancelledError:
            logger.info("завершение работы ...")
        finally:
            await pubsub.unsubscribe(*channels)
            await client.aclose()
            logger.info("подписка отменена, коннект закрыт")


if __name__ == "__main__":
    try:
        asyncio.run(start_debug_subscriber())
    except KeyboardInterrupt:
        logger.info("Слушатель остановлен.")
