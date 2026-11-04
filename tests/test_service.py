# tests/test_service.py
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.device_provider.repository import Result
from apps.device_provider.service import DeviceProviderService
from libs.events.models import DeviceConfig


# Кастомный асинхронный генератор для подмены DeviceLoader
async def mock_devices_generator(*args, **kwargs):
    yield DeviceConfig(uid="router-01", ip="1.1.1.1", check_type="icmp")
    yield DeviceConfig(uid="switch-02", ip="2.2.2.2", check_type="port", port=22)


@pytest.mark.asyncio
async def test_service_sync_flows():
    """Тест оркестрации сервиса: проверка разбора результатов 'created' и 'updated'."""

    # 1. Создаем моки зависимостей
    mock_loader = MagicMock()
    mock_loader.devices = mock_devices_generator

    mock_repo = MagicMock()
    # Настраиваем поочередный возврат результатов для двух девайсов из генератора
    mock_repo.upsert_device = AsyncMock()
    mock_repo.upsert_device.side_effect = [
        Result(action="created"),
        Result(action="updated", old_value=DeviceConfig(uid="switch-02", ip="2.2.2.0", check_type="port")),
    ]

    mock_notifier = MagicMock()
    mock_notifier.send_device_created = AsyncMock()
    mock_notifier.send_device_updated = AsyncMock()

    # 2. Инжектируем моки в сервис
    service = DeviceProviderService(
        loader=mock_loader,
        repository=mock_repo,
        notifier=mock_notifier,
    )

    # 3. Выполняем синхронизацию
    await service.sync_configuration()

    # 4. Проверяем, что сервис вызвал правильные методы извещателя для каждого случая
    assert mock_repo.upsert_device.call_count == 2
    mock_notifier.send_device_created.assert_called_once()
    mock_notifier.send_device_updated.assert_called_once()


@pytest.mark.asyncio
async def test_service_handles_repository_exception(caplog):
    """Крайний случай: Если на одном устройстве репозиторий падает с ошибкой, цикл должен продолжить работу."""
    mock_loader = MagicMock()
    mock_loader.devices = mock_devices_generator

    mock_repo = MagicMock()
    # Первое устройство падает по ошибке базы, второе проходит успешно
    mock_repo.upsert_device = AsyncMock()
    mock_repo.upsert_device.side_effect = [
        Exception("Valkey Connection Lost!"),
        Result(action="none"),
    ]

    mock_notifier = MagicMock()
    mock_notifier.send_device_created = AsyncMock()

    service = DeviceProviderService(
        loader=mock_loader,
        repository=mock_repo,
        notifier=mock_notifier,
        logger=logging.getLogger(__name__),
    )

    # Запускаем и проверяем, что падения всего сервиса не произошло
    await service.sync_configuration()

    # Убеждаемся, что вторая запись была успешно обработана, несмотря на ошибку первой
    assert mock_repo.upsert_device.call_count == 2
    assert "Ошибка при сохранении устройства router-01" in caplog.text
