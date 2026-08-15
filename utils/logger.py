"""Application-wide logging configuration."""

from __future__ import annotations

import logging
import os
import traceback


class SecretRedactionFilter(logging.Filter):
    """Prevent configured secret values from appearing in application logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        token = os.getenv("BOT_TOKEN", "")
        if not token:
            return True

        message = record.getMessage()
        exception_text = ""
        if record.exc_info:
            exception_text = "".join(traceback.format_exception(*record.exc_info))

        if token in message:
            record.msg = message.replace(token, "[REDACTED]")
            record.args = ()
        if token in exception_text:
            record.exc_info = None
            record.exc_text = None
        return True


def configure_logging() -> logging.Logger:
    """Configure safe, readable logs without printing secret values."""

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    redaction_filter = SecretRedactionFilter()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    for logger_name in ("", "telegram", "telegram.ext", "httpx", "httpcore"):
        logging.getLogger(logger_name).addFilter(redaction_filter)
    return logging.getLogger("cyberbot")


logger = configure_logging()