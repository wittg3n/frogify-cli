from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from frogify.config import ConfigManager

_SENSITIVE = re.compile(
    r"([?&](?:access_token|auth|key|signature|sig|token)=)[^&\s\"']+", re.IGNORECASE
)


def redact(text: str) -> str:
    return _SENSITIVE.sub(r"\1<redacted>", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(config: ConfigManager, *, debug: bool = False) -> logging.Logger:
    config.ensure_directories()
    logger = logging.getLogger("frogify")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        handler = RotatingFileHandler(
            config.log_dir / "frogify.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
