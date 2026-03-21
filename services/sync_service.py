"""
services/sync_service.py

Desktop-side sync orchestrator.
Reads from the outbox, pushes to the backend's /sync/push endpoint,
and pulls incremental updates from /sync/pull.

Integrates with the backend's idempotent sync engine:
  - SyncPushRequest: { operations: [{ id, entity, action, payload, updated_at }] }
  - SyncPullResponse: { items, sales, attendance, raw_materials }
"""

import json
import logging
from datetime import datetime, timezone

from services.api_client import APIClient
from services.session import Session
from database.local_db import LocalDB
from database.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


class SyncService:
    """Push/Pull sync orchestrator for the desktop client."""

    def __init__(self, api: APIClient | None = None, db: LocalDB | None = None):
        self._api = api or APIClient()
        self._db = db or LocalDB()
        self._outbox = OutboxRepository(self._db)

    # ------------------------------------------------------------------
    # Online check
    # ------------------------------------------------------------------
    def is_online(self) -> bool:
        """Check if the backend is reachable."""
        return self._api.health_check()

    # ------------------------------------------------------------------
    # Push: outbox → backend
    # ------------------------------------------------------------------
    def push_sync(self) -> dict:
        """
        Push all pending outbox entries to the backend.
        Returns { "pushed": int, "failed": int } stats.
        """
        token = Session.get_token()
        if not token:
            return {"pushed": 0, "failed": 0, "error": "Not authenticated"}

        pending = self._outbox.get_pending()
        if not pending:
            return {"pushed": 0, "failed": 0}

        # Build operations matching the backend's SyncOperation schema
        operations = []
        for entry in pending:
            operations.append(
                {
                    "id": entry.id,
                    "entity": entry.entity,
                    "action": entry.action,
                    "payload": json.loads(entry.payload),
                    "updated_at": entry.created_at,
                }
            )

        result = self._api.push_sync(token, operations)

        pushed = 0
        failed = 0

        if result:
            # Mark successful entries
            for op_result in result.get("success", []):
                client_id = op_result.get("client_id")
                if client_id:
                    self._outbox.mark_synced(client_id)
                    pushed += 1

            # Mark failed entries
            for op_result in result.get("failed", []):
                client_id = op_result.get("client_id")
                error = op_result.get("error", "Unknown error")
                if client_id:
                    self._outbox.mark_failed(client_id, error)
                    failed += 1

            logger.info(f"Sync push complete: {pushed} synced, {failed} failed")
        else:
            failed = len(pending)
            logger.warning("Sync push failed — backend unreachable or returned error")

        return {"pushed": pushed, "failed": failed}

    # ------------------------------------------------------------------
    # Pull: backend → local
    # ------------------------------------------------------------------
    def pull_sync(self) -> dict:
        """
        Pull incremental updates from the backend since last sync.
        Returns the SyncPullResponse dict or an error dict.
        """
        token = Session.get_token()
        if not token:
            return {"error": "Not authenticated"}

        last_sync = self._outbox.get_last_sync()
        if not last_sync:
            # First sync ever — pull everything from epoch
            last_sync = "2000-01-01T00:00:00+00:00"

        result = self._api.pull_sync(token, last_sync)
        if result is None:
            return {"error": "Pull sync failed"}

        # Update last sync timestamp
        now = datetime.now(timezone.utc).isoformat()
        self._outbox.set_last_sync(now)
        Session.set_last_sync(datetime.now(timezone.utc))

        logger.info(
            f"Pull sync complete: {len(result.get('items', []))} items, "
            f"{len(result.get('sales', []))} sales"
        )
        return result

    # ------------------------------------------------------------------
    # Queue an operation for later push
    # ------------------------------------------------------------------
    def queue_operation(self, entity: str, action: str, payload: dict) -> int:
        """Add an operation to the outbox for later sync. Returns entry ID."""
        return self._outbox.add_entry(entity, action, payload)
