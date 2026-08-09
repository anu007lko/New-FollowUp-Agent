"""
Redacted structured logging module.
Redacts tokens, email bodies, secrets, and authorization headers from logs.
"""

import json
import logging
import re
from typing import Any, Dict

SENSITIVE_PATTERNS = [
    re.compile(r'(?i)"(authorization|token|secret|password|cookie|access_token|refresh_token|client_secret)":\s*"[^"]*"'),
    re.compile(r'(?i)Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*')
]

SENSITIVE_KEYS = {
    "authorization", "token", "secret", "password", "cookie",
    "access_token", "refresh_token", "client_secret", "body", "headers", "key"
}


class RedactedJSONFormatter(logging.Formatter):
    """Logging formatter that converts records to JSON and redacts sensitive data."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact_string(record.getMessage())
        }

        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_entry["details"] = self._redact_dict(record.extra_data)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)

    def _redact_string(self, text: str) -> str:
        for pattern in SENSITIVE_PATTERNS:
            text = pattern.sub('[REDACTED]', text)
        return text

    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        redacted = {}
        for key, value in data.items():
            if key.lower() in SENSITIVE_KEYS:
                redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            elif isinstance(value, str):
                redacted[key] = self._redact_string(value)
            else:
                redacted[key] = value
        return redacted


def setup_redacted_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(RedactedJSONFormatter())
        logger.addHandler(handler)
    return logger
