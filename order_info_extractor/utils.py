"""Shared utility helpers."""

from __future__ import annotations

import hashlib
import html
import json
import random
import re
import time
from datetime import datetime
from typing import Any, Callable, Iterable, Optional, TypeVar

from order_info_extractor.models import InboxMessage

T = TypeVar("T")


def clean_html(value: str) -> str:
    """Strip simple HTML tags and normalize whitespace."""

    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str) -> str:
    """Normalize common date formats to ISO format when possible."""

    if not value:
        return ""

    candidates = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    )
    value = value.strip()
    for fmt in candidates:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def erp_date(value: str) -> str:
    """Format a date in the ERP-friendly M/D/YYYY format."""

    normalized = parse_date(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return f"{parsed.month}/{parsed.day}/{parsed.year}"
        except ValueError:
            continue
    return value or datetime.utcnow().strftime("%-m/%-d/%Y")


def stable_hash(parts: Iterable[Any]) -> str:
    """Return a sha256 hash for a sequence of JSON-serializable parts."""

    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, bytes):
            payload = part
        else:
            payload = json.dumps(part, sort_keys=True, default=str).encode("utf-8")
        digest.update(payload)
        digest.update(b"\n")
    return digest.hexdigest()


def message_hash(message: InboxMessage) -> str:
    """Create a deterministic hash for the message payload."""

    attachment_fingerprints = [
        {
            "filename": attachment.filename,
            "hash": stable_hash([attachment.content_bytes]),
        }
        for attachment in message.attachments
    ]
    return stable_hash(
        [
            message.subject,
            message.sender.model_dump(),
            message.received_at,
            message.body,
            attachment_fingerprints,
        ]
    )


def retry_with_backoff(
    func: Callable[[], T],
    attempts: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    jitter_ratio: float,
    retryable_exceptions: tuple[type[BaseException], ...],
) -> T:
    """Run a callable with exponential backoff and jitter."""

    delay = max(base_delay_seconds, 0.0)
    last_error: Optional[BaseException] = None

    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retryable_exceptions as exc:
            last_error = exc
            if attempt == attempts:
                break
            jitter = delay * jitter_ratio * random.random()
            time.sleep(min(max_delay_seconds, delay + jitter))
            delay = min(max_delay_seconds, max(delay * 2, base_delay_seconds))

    if last_error is None:
        raise RuntimeError("retry_with_backoff exhausted without capturing an error")
    raise last_error

