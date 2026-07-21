from __future__ import annotations

import logging
from collections.abc import Callable


class CallbackHandler(logging.Handler):
    def __init__(self, callback: Callable[[str, str], None]) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        self.callback(record.levelname, self.format(record))


def configure_logging(callback: Callable[[str, str], None]) -> logging.Logger:
    logger = logging.getLogger("salsilink")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = CallbackHandler(callback)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger
