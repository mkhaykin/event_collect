# apps/device_provider/config.py
import os


class Config:
    VALKEY_DSN = os.environ.get("VALKEY_DSN", "redis://localhost:6379/0")


config = Config()
