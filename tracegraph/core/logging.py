import json
import logging
from datetime import UTC, datetime

from tracegraph.core.context import get_request_id

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """
    #Feature: Observability
    #Scenario: Emit one JSON object per log line including extra context fields
    #Complexity: Time O(k) - linear in number of extra fields

    Structured JSON log formatter.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        #Feature: Observability
        #Scenario: Serialise a log record with its extras and the bound request id
        #Complexity: Time O(k) - linear in number of extra fields

        Args:
            record: Log record to format.

        Returns:
            JSON string.
        """
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        payload.setdefault("request_id", get_request_id())
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """
    #Feature: Observability
    #Scenario: Install the JSON formatter on the root logger once at startup
    #Complexity: Time O(1) - constant

    Args:
        level: Log level name such as INFO.

    Raises:
        ValueError: When level is None or not a valid level name.
    """
    if level is None:
        raise ValueError("[configure_logging] 'level' is required and must not be None.")
    if level.upper() not in logging.getLevelNamesMapping():
        raise ValueError(f"[configure_logging] Unknown log level {level!r}. Fix: use DEBUG, INFO, WARNING or ERROR.")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
