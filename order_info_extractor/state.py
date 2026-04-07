"""SQLite-backed idempotency store."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from order_info_extractor.models import ProcessedOrder


class SQLiteStateStore:
    """Track processed messages so repeated runs stay idempotent."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.database_path))

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_orders (
                    idempotency_key TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    export_path TEXT,
                    review_path TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def lookup(self, idempotency_key: str, source_hash: str) -> Optional[Dict[str, str]]:
        """Return a stored record when the payload hash matches."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT message_id, source_hash, status, confidence, export_path, review_path
                FROM processed_orders
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()

        if row is None or row[1] != source_hash:
            return None

        return {
            "message_id": row[0],
            "source_hash": row[1],
            "status": row[2],
            "confidence": row[3],
            "export_path": row[4] or "",
            "review_path": row[5] or "",
        }

    def record(self, processed_order: ProcessedOrder) -> None:
        """Upsert the latest processing outcome."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO processed_orders (
                    idempotency_key,
                    message_id,
                    source_hash,
                    status,
                    confidence,
                    export_path,
                    review_path,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    message_id = excluded.message_id,
                    source_hash = excluded.source_hash,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    export_path = excluded.export_path,
                    review_path = excluded.review_path,
                    updated_at = excluded.updated_at
                """,
                (
                    processed_order.idempotency_key,
                    processed_order.message_id,
                    processed_order.source_hash,
                    processed_order.status,
                    processed_order.confidence,
                    processed_order.export_path,
                    processed_order.review_path,
                    datetime.utcnow().isoformat(timespec="seconds") + "Z",
                ),
            )

