"""Redact structured audit details without retaining the original input object."""
import os
import re
from typing import Any


_SENSITIVE = re.compile(r"password|secret|token|api[_-]?key|authorization|cookie|ciphertext", re.I)
_PROVIDER_KEY = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,})\b")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _SENSITIVE.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        result = _PROVIDER_KEY.sub("[REDACTED]", value)
        for name, secret in os.environ.items():
            if len(secret) >= 8 and _SENSITIVE.search(name):
                result = result.replace(secret, "[REDACTED]")
        return result
    return value
