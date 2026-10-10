"""Sanitized, structured diagnostics for metadata enrichment."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_SECRET = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret)"
    r"([\s=:]+)([^\s&,;]+)"
)


def sanitize_error(value: Any) -> str:
    """Remove common credential-like values before persistence or display."""
    text = str(value or "").strip()
    return _SECRET.sub(r"\1\2[REDACTED]", text)[:1000]


def classify_failure(error: Any, *, stage: str = "metadata") -> str:
    """Map provider, network and persistence errors to actionable categories."""
    message = str(error or "").lower()
    status = getattr(error, "status_code", None)
    if stage == "poster":
        return "image_download_failure"
    if stage == "persistence":
        return "database_persistence_failure"
    if "no matching metadata" in message or "not found" in message:
        return "no_matching_title"
    if status == 429:
        return "http_429_rate_limited"
    if status in (401, 403):
        return "provider_auth_or_configuration"
    if isinstance(status, int) and 400 <= status < 500:
        return "http_4xx_client_error"
    if isinstance(status, int) and status >= 500:
        return "http_5xx_server_error"
    name = type(error).__name__.lower()
    if "timeout" in name or "timed out" in message or "timeout" in message:
        return "connection_timeout"
    if any(token in message for token in ("dns", "network", "connection", "urlerror", "name resolution")):
        return "dns_or_network_failure"
    if any(token in message for token in ("json", "malformed", "unexpected response", "usable title")):
        return "malformed_api_response"
    if "cancel" in message:
        return "cancelled_task"
    return "unknown_error"


def failure_record(*, item: Any, node: Any, error: Any, stage: str = "metadata", provider: str = "") -> dict:
    """Create a secret-scrubbed report row, never including credentials."""
    return {
        "title": str(getattr(item, "title", "") or getattr(node, "title", "Untitled")),
        "media_type": str(getattr(item, "category", "") or getattr(node, "media_type", "unknown")),
        "provider": str(provider or getattr(error, "provider", "") or "provider-chain"),
        "stage": stage,
        "category": classify_failure(error, stage=stage),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempt_count": max(1, int(getattr(node, "retry_count", 0)) + 1),
        "error": sanitize_error(error),
        "item_id": getattr(item, "id", None),
    }
