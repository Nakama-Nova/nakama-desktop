"""
database/models.py

Plain dataclasses for local database records.
No SQLAlchemy dependency — uses Python's built-in sqlite3.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class OutboxEntry:
    """A pending sync operation queued for push to the backend."""

    entity: str  # "sale", "item", "attendance", "raw_material"
    action: str  # "create", "update", "delete"
    payload: str  # JSON-encoded payload
    status: str = "pending"  # "pending", "synced", "failed"
    id: str = ""  # Auto-assigned by DB
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error_message: str | None = None


@dataclass
class SyncMetadata:
    """Tracks the last successful sync timestamp."""

    last_sync_at: str = ""  # ISO-8601 UTC timestamp
