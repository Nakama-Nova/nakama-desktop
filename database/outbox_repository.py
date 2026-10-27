"""
database/outbox_repository.py

Data access for the sync outbox queue.
Pure repository — no business logic, no API calls.
"""

import json
import uuid
from datetime import datetime, timezone

from database.local_db import LocalDB
from database.models import OutboxEntry


class OutboxRepository:
    """CRUD operations on the local outbox table."""

    def __init__(self, db: LocalDB | None = None):
        self._db = db or LocalDB()

    def _conn(self):
        return self._db.get_connection()

    def add_entry(
        self,
        entity: str,
        action: str,
        payload: dict,
        entry_id: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Queue a new outbox operation. Returns the entry's id.

        The id is a UUID generated here (not SQLite's rowid) because it
        doubles as the sync engine's idempotency key (client_id) once
        pushed — a per-install autoincrement integer would collide across
        multiple desktop installs pushing to the same backend.

        entry_id lets a caller reuse the id it already sent to the server (a sale
        whose online attempt may have gone through), so the server recognises
        the replay instead of recording it twice.

        user_id is who made the change. The server records a pushed change under
        whoever's token pushes it, so the row must only be pushed by that user.
        """
        entry_id = entry_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn().execute(
            "INSERT INTO outbox (id, entity, action, payload, status, created_at, user_id) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (entry_id, entity, action, json.dumps(payload), now, user_id),
        )
        self._conn().commit()
        return entry_id

    def get_pending(self) -> list[OutboxEntry]:
        """Return all entries with status='pending', ordered FIFO."""
        # Order by rowid (SQLite's implicit, monotonically-increasing insert
        # order) rather than id — id is now a random UUID, not a sortable
        # sequence, since it doubles as the sync idempotency key.
        rows = (
            self._conn()
            .execute("SELECT * FROM outbox WHERE status = 'pending' ORDER BY rowid ASC")
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
                user_id=row["user_id"],
            )
            for row in rows
        ]

    def claim(self, entry_id: str, user_id: str) -> None:
        """Give a row queued before attribution existed to a user (once)."""
        self._conn().execute(
            "UPDATE outbox SET user_id = ? WHERE id = ? AND user_id IS NULL",
            (user_id, entry_id),
        )
        self._conn().commit()

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
