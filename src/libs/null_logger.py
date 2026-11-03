# libs/null_logger.py
import logging


class NullLogger(logging.Logger):
    def __init__(self, name: str = "null") -> None:
        super().__init__(name, level=logging.NOTSET)
        self.propagate = False

    def handle(self, record: logging.LogRecord) -> None:
        pass

    def isEnabledFor(self, level: int) -> bool:  # noqa: ARG002
        return False
