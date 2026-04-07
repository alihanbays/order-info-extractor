"""Structured logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for local observability and CI logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = getattr(record, "event")
        if hasattr(record, "message_id"):
            payload["message_id"] = getattr(record, "message_id")
        if hasattr(record, "status"):
            payload["status"] = getattr(record, "status")
        if hasattr(record, "confidence"):
            payload["confidence"] = getattr(record, "confidence")
        return json.dumps(payload, sort_keys=True)


def configure_logging(log_dir: Path, logger_name: str = "order_info_extractor") -> tuple[logging.Logger, Path]:
    """Configure a JSON logger that writes both to stdout and a log file."""

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline.jsonl"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()
    logger.propagate = False

    formatter = JsonFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger, log_path
