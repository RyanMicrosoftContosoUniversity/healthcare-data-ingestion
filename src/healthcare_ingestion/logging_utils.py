"""Scoped structured events, independent from authoritative execution persistence."""

import contextvars
import json
import logging
from contextlib import contextmanager
from datetime import UTC, datetime

_CONTEXT = contextvars.ContextVar("healthcare_logging_context", default={})


@contextmanager
def logging_context(**values):
    if any(not isinstance(value, (str, int, bool, type(None))) for value in values.values()):
        raise ValueError("Logging context accepts identifiers, not arbitrary source records.")
    token = _CONTEXT.set({**_CONTEXT.get(), **values})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            "TimeGenerated": datetime.now(UTC).isoformat(),
            "Level": record.levelname,
            "Event": record.getMessage(),
            **_CONTEXT.get(),
        }
        if record.exc_info:
            # Record the class, not source rows, tokens or arbitrary connection-string messages.
            event["ExceptionType"] = record.exc_info[0].__name__
        return json.dumps(event, ensure_ascii=True, separators=(",", ":"))


def configure_logging(level="INFO", stream=None):
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Invalid logging level.")
    logger = logging.getLogger("healthcare_ingestion")
    if not any(getattr(handler, "_healthcare_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler(stream)
        handler._healthcare_handler = True
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


class DriverJvmHandler(logging.Handler):
    def __init__(self, spark):
        super().__init__()
        if getattr(spark, "_jvm", None) is None:
            raise ValueError("A driver JVM is required for the log4j bridge.")
        self.logger = spark._jvm.org.apache.logging.log4j.LogManager.getLogger(
            "healthcare_ingestion"
        )

    def emit(self, record):
        methods = {
            logging.DEBUG: "debug",
            logging.INFO: "info",
            logging.WARNING: "warn",
            logging.ERROR: "error",
            logging.CRITICAL: "fatal",
        }
        try:
            getattr(self.logger, methods.get(record.levelno, "info"))(self.format(record))
        except Exception:
            self.handleError(record)
