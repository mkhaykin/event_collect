"""
Тесты для сбора моделек конфига:
- проверка поведения при наличии / отсутствии uid и name.
"""

from libs.models.config import DeviceConfig


def test_empty_model_uid() -> None:
    dev = DeviceConfig(uid="router-x", ip="10.0.0.1", check_type="icmp")
    assert dev.uid == "router-x"
    assert dev.name == "router-x"
    assert dev.ip == "10.0.0.1"


def test_empty_model_name() -> None:
    dev = DeviceConfig(name="router-x", ip="10.0.0.1", check_type="icmp")
    # точно проверить не можем, так как обрезаем uid, поэтому вот так
    # assert re.match(r"^[0-9a-f]{8}$", dev.uid)
    assert dev.uid == "router-x"
    assert dev.name == "router-x"
    assert dev.ip == "10.0.0.1"


def test_empty_model() -> None:
    dev = DeviceConfig(uid="some_uid", name="router-x", ip="10.0.0.1", check_type="icmp")
    assert dev.uid == "some_uid"
    assert dev.name == "router-x"
    assert dev.ip == "10.0.0.1"
