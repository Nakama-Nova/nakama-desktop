"""
database/local_db.py

SQLite connection manager for offline caching and outbox queue.
Uses Python's built-in sqlite3 — zero additional dependencies.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "nakama_local.db"


class LocalDB:
    """SQLite connection manager and schema bootstrapper."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def get_connection(self) -> sqlite3.Connection:
        """Return a reusable connection (lazy-initialized)."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self.initialize_tables()
        return self._conn

    def initialize_tables(self) -> None:
        """Create tables if they don't exist yet."""
        conn = self._conn or sqlite3.connect(str(self._db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS outbox (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entity      TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                payload     TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_metadata (
                id              INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_at    TEXT NOT NULL DEFAULT ''
            );

            -- Ensure exactly one metadata row exists
            INSERT OR IGNORE INTO sync_metadata (id, last_sync_at) VALUES (1, '');
        """)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
