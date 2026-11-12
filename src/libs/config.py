# apps/device_provider/config.py
import os


class Config:
    VALKEY_DSN = os.environ.get("VALKEY_DSN", "redis://localhost:6379/0")

    """
    device:all — Set.
    device:config:{uid} — String (json).
    device:heartbeat:{uid} — Hash.
    """
    CONFIG_ALL_DEVICE: str = "device:all"
    CONFIG_SPECIFIC_DEVICE: str = "device:config:{uid}"
    CONFIG_HEARTBEAT: str = "device:heartbeat:{uid}"
    CONFIG_DEVICE_TTL: int = 480

    CONFIG_EVENT_CREATED: str = "events:device_created"
    CONFIG_EVENT_UPDATED: str = "events:device_updated"
    CONFIG_EVENT_DELETED: str = "events:device_deleted"

    CONFIG_EVENT_ONLINE: str = "events:device_online"
    CONFIG_EVENT_OFFLINE: str = "events:device_offline"

    POLLER_FAIL_COUNT: int = 3
    POLLER_SUCCESS_COUNT: int = 3

    CONCURRENCY_LIMIT: int = 20


config = Config()
