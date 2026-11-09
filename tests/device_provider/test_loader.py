# tests/test_loader.py
from pathlib import Path

import pytest

from apps.device_provider.loader import DeviceYamlLoader
from libs.events.models import DeviceConfig


@pytest.mark.asyncio
async def test_loader_success(tmp_path: Path):
    """Проверка успешной загрузки валидного YAML."""
    yaml_content = """
    devices:
      - uid: "router-01"
        ip: "192.168.1.1"
        check_type: "icmp"
    """
    config_file = tmp_path / "devices.yaml"
    config_file.write_text(yaml_content)

    loader = DeviceYamlLoader(config_file)
    devices = [d async for d in loader.devices(schema=DeviceConfig)]

    assert len(devices) == 1
    assert devices[0].uid == "router-01"
    assert devices[0].ip == "192.168.1.1"


@pytest.mark.asyncio
async def test_loader_file_not_found():
    """Крайний случай: Файл конфигурации не существует."""
    loader = DeviceYamlLoader("non_existent_file.yaml")
    with pytest.raises(ValueError, match="Файл конфигурации не найден"):
        async for _ in loader.devices(schema=DeviceConfig):
            pass


@pytest.mark.asyncio
async def test_loader_missing_devices_key(tmp_path: Path):
    """Крайний случай: В YAML нет корневого ключа 'devices'."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text("invalid_root: []")

    loader = DeviceYamlLoader(config_file)
    with pytest.raises(ValueError, match="Нет ключа `devices`"):
        async for _ in loader.devices(schema=DeviceConfig):
            pass


@pytest.mark.asyncio
async def test_loader_empty_devices_list(tmp_path: Path):
    """Крайний случай: Список устройств пуст."""
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("devices: []")

    loader = DeviceYamlLoader(config_file)
    devices = [d async for d in loader.devices(schema=DeviceConfig)]
    assert len(devices) == 0


@pytest.mark.asyncio
async def test_loader_skips_partial_invalid_device(tmp_path: Path):
    """Крайний случай: Одно устройство валуется с ошибкой, остальные должны прочитаться."""
    yaml_content = """
    devices:
      - uid: "bad-router"
        ip: "not-an-ip"
        check_type: "invalid_type"
      - uid: "good-router"
        ip: "10.0.0.1"
        check_type: "port"
        port: 80
    """
    config_file = tmp_path / "partial.yaml"
    config_file.write_text(yaml_content)

    loader = DeviceYamlLoader(config_file)
    devices = [d async for d in loader.devices(schema=DeviceConfig)]

    assert len(devices) == 1
    assert devices[0].uid == "good-router"
