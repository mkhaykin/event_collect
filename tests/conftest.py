# tests/conftest.py
import asyncio

import pytest
import pytest_asyncio
import redis.asyncio as valkey
from testcontainers.redis import RedisContainer


# Настройка pytest-asyncio для использования единого event loop на сессию
@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# Запуск живого Valkey/Redis контейнера
@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("valkey/valkey:8.0-alpine") as container:
        yield container


# Получение динамического DSN адреса контейнера
@pytest.fixture(scope="session")
def valkey_dsn(redis_container) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


# Чистка базы перед каждым тестом для обеспечения 100% изоляции
@pytest_asyncio.fixture(autouse=True)
async def clear_valkey(valkey_dsn):
    client = valkey.from_url(valkey_dsn)
    await client.flushdb()
    await client.aclose()
