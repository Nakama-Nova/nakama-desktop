"""
database/outbox_repository.py

Data access for the sync outbox queue.
Pure repository — no business logic, no API calls.
"""

import json
from datetime import datetime, timezone

from database.local_db import LocalDB
from database.models import OutboxEntry


class OutboxRepository:
    """CRUD operations on the local outbox table."""

    def __init__(self, db: LocalDB | None = None):
        self._db = db or LocalDB()

    def _conn(self):
        return self._db.get_connection()

    def add_entry(self, entity: str, action: str, payload: dict) -> int:
        """Queue a new outbox operation. Returns the row ID."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn().execute(
            "INSERT INTO outbox (entity, action, payload, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (entity, action, json.dumps(payload), now),
        )
        self._conn().commit()
        return cursor.lastrowid

    def get_pending(self) -> list[OutboxEntry]:
        """Return all entries with status='pending', ordered FIFO."""
        rows = (
            self._conn()
            .execute("SELECT * FROM outbox WHERE status = 'pending' ORDER BY id ASC")
            .fetchall()
        )
        return [
            OutboxEntry(
                id=str(row["id"]),
                entity=row["entity"],
                action=row["action"],
                payload=row["payload"],
                status=row["status"],
                created_at=row["created_at"],
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def mark_synced(self, entry_id: str) -> None:
        self._conn().execute(
            "UPDATE outbox SET status = 'synced' WHERE id = ?", (entry_id,)
        )
        self._conn().commit()

    def mark_failed(self, entry_id: str, error: str) -> None:
        self._conn().execute(
            "UPDATE outbox SET status = 'failed', error_message = ? WHERE id = ?",
            (error, entry_id),
        )
        self._conn().commit()

    def get_last_sync(self) -> str:
        """Return the ISO-8601 last sync timestamp, or '' if never synced."""
        row = (
            self._conn()
            .execute("SELECT last_sync_at FROM sync_metadata WHERE id = 1")
            .fetchone()
        )
        return row["last_sync_at"] if row else ""

    def set_last_sync(self, ts: str) -> None:
        self._conn().execute(
            "UPDATE sync_metadata SET last_sync_at = ? WHERE id = 1", (ts,)
        )
        self._conn().commit()
