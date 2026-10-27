"""
The server records a pushed bill under whoever's token pushes it. So a bill queued by
user A must only ever be pushed by A: the outbox remembers who queued each row, other
users' rows are held (not sent, not failed, not lost), and the server's own refusal of
a mismatch keeps the row queued too.
"""

import base64
import json
import sqlite3
import time

import pytest

import services.session as sess
from database.local_db import LocalDB
from database.outbox_repository import OutboxRepository
from services.enums import UserRole
from services.sales_service import SalesService
from services.session import Session
from services.sync_service import SyncService

LINES = [{"item_id": "11111111-1111-1111-1111-111111111111", "quantity": 1, "price": 100.0}]
ASHA, BALU = "11111111-aaaa-4aaa-8aaa-111111111111", "22222222-bbbb-4bbb-8bbb-222222222222"


def jwt(sub):
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{seg({'alg': 'HS256'})}.{seg({'sub': sub, 'exp': time.time() + 3600})}.sig"


def sign_in_as(monkeypatch, user_id, role=UserRole.SALES):
    monkeypatch.setattr(Session, "_token", jwt(user_id) if user_id else "test-token")
    monkeypatch.setattr(Session, "_role", role)


class FakeApi:
    """Records what is pushed; answers every operation with `outcome`."""

    def __init__(self, outcome="success"):
        self.outcome, self.sent = outcome, []

    def push_sync(self, token, operations):
        self.sent.extend(operations)
        rows = [{"client_id": o["id"], "status": self.outcome, "error": "nope"} for o in operations]
        if self.outcome == "success":
            return {"success": rows, "failed": []}
        return {"success": [], "failed": rows}


def statuses():
    conn = LocalDB().get_connection()
    return {r["id"]: (r["status"], r["user_id"]) for r in conn.execute("select * from outbox")}


# --- who is signed in ----------------------------------------------------------------


def test_the_signed_in_user_id_comes_from_the_token(monkeypatch):
    sign_in_as(monkeypatch, ASHA)
    assert Session.get_user_id() == ASHA


@pytest.mark.parametrize("token", [None, "", "not-a-jwt", "a.b.c", "a." + "!!" + ".c"])
def test_no_user_id_when_the_token_is_missing_or_unreadable(monkeypatch, token):
    monkeypatch.setattr(Session, "_token", token)
    assert Session.get_user_id() is None


def test_token_expiry_check_still_works_after_the_refactor():
    assert sess._is_token_expired(jwt("u")) is False
    assert sess._is_token_expired("garbage") is True
    assert sess._is_token_expired("h.e30.s") is True  # payload {}: no exp


# --- queuing ---------------------------------------------------------------------------


def test_an_offline_sale_remembers_who_rang_it_up(monkeypatch):
    sign_in_as(monkeypatch, ASHA)
    SalesService().queue_offline_sale(LINES, "Meena", "9876543210")
    (entry,) = OutboxRepository().get_pending()
    assert entry.user_id == ASHA


def test_the_outbox_id_and_the_user_are_independent(monkeypatch):
    sign_in_as(monkeypatch, ASHA)
    SalesService().queue_offline_sale(LINES, "Meena", "9876543210", client_id="abc-123")
    (entry,) = OutboxRepository().get_pending()
    assert (entry.id, entry.user_id) == ("abc-123", ASHA)


# --- an existing database gets the new column -----------------------------------------


def test_an_outbox_from_before_attribution_is_upgraded_in_place(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        """CREATE TABLE outbox (id TEXT PRIMARY KEY, entity TEXT NOT NULL, action TEXT NOT NULL,
           payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', error_message TEXT,
           created_at TEXT NOT NULL);
           INSERT INTO outbox (id, entity, action, payload, created_at)
           VALUES ('legacy-1', 'sale', 'create', '{}', '2026-10-01T00:00:00+00:00');"""
    )
    old.commit()
    old.close()

    (entry,) = OutboxRepository(LocalDB(path)).get_pending()

    assert entry.id == "legacy-1" and entry.user_id is None  # kept, unattributed


# --- pushing ---------------------------------------------------------------------------


def two_bills(monkeypatch):
    """One bill queued by Asha and one by Balu."""
    ids = {}
    for name, uid in (("asha", ASHA), ("balu", BALU)):
        sign_in_as(monkeypatch, uid)
        SalesService().queue_offline_sale(LINES, name, "9000000000")
    for entry in OutboxRepository().get_pending():
        ids[entry.user_id] = entry.id
    return ids[ASHA], ids[BALU]


def test_a_push_sends_only_the_signed_in_users_bills_and_holds_the_rest(monkeypatch):
    asha_bill, balu_bill = two_bills(monkeypatch)
    sign_in_as(monkeypatch, BALU)
    api = FakeApi()

    result = SyncService(api=api).push_sync()

    assert [o["id"] for o in api.sent] == [balu_bill]
    assert api.sent[0]["user_id"] == BALU  # the server can double-check
    assert result == {"pushed": 1, "failed": 0, "held": 1}
    assert statuses()[asha_bill] == ("pending", ASHA)  # untouched, not failed
    assert statuses()[balu_bill][0] == "synced"


def test_the_held_bill_goes_when_its_owner_signs_in_again(monkeypatch):
    asha_bill, _ = two_bills(monkeypatch)
    sign_in_as(monkeypatch, BALU)
    SyncService(api=FakeApi()).push_sync()

    sign_in_as(monkeypatch, ASHA)
    api = FakeApi()
    result = SyncService(api=api).push_sync()

    assert [o["id"] for o in api.sent] == [asha_bill] and api.sent[0]["user_id"] == ASHA
    assert result == {"pushed": 1, "failed": 0, "held": 0}


def test_when_everything_is_someone_elses_nothing_is_sent_at_all(monkeypatch):
    two_bills(monkeypatch)
    sign_in_as(monkeypatch, "33333333-cccc-4ccc-8ccc-333333333333")
    api = FakeApi()
    assert SyncService(api=api).push_sync() == {"pushed": 0, "failed": 0, "held": 2}
    assert api.sent == []


def test_a_user_whose_id_is_unknown_cannot_push_anyones_attributed_bills(monkeypatch):
    two_bills(monkeypatch)
    sign_in_as(monkeypatch, None)  # a token without a readable subject
    api = FakeApi()
    assert SyncService(api=api).push_sync()["held"] == 2 and api.sent == []


def test_the_server_refusing_a_bill_as_someone_elses_keeps_it_queued(monkeypatch):
    asha_bill, balu_bill = two_bills(monkeypatch)
    sign_in_as(monkeypatch, ASHA)
    result = SyncService(api=FakeApi(outcome="wrong_user")).push_sync()

    # Balu's bill is held here; Asha's is held because the server said it isn't hers
    assert result == {"pushed": 0, "failed": 0, "held": 2}
    assert statuses()[asha_bill][0] == "pending"  # not marked failed: nothing is lost
    assert statuses()[balu_bill][0] == "pending"


def test_a_real_server_failure_is_still_marked_failed(monkeypatch):
    asha_bill, _ = two_bills(monkeypatch)
    sign_in_as(monkeypatch, ASHA)
    result = SyncService(api=FakeApi(outcome="failed")).push_sync()
    assert result["failed"] == 1 and statuses()[asha_bill][0] == "failed"


def test_bills_queued_before_attribution_are_taken_over_once_by_the_first_user(monkeypatch):
    OutboxRepository().add_entry("sale", "create", {"id": "s"}, entry_id="legacy-1")  # no user
    sign_in_as(monkeypatch, ASHA)
    api = FakeApi()
    SyncService(api=api).push_sync()

    assert api.sent[0]["id"] == "legacy-1" and api.sent[0]["user_id"] == ASHA
    assert statuses()["legacy-1"] == ("synced", ASHA)


def test_without_a_known_user_old_unattributed_rows_still_push_without_a_maker(monkeypatch):
    OutboxRepository().add_entry("sale", "create", {"id": "s"}, entry_id="legacy-1")
    sign_in_as(monkeypatch, None)
    api = FakeApi()
    SyncService(api=api).push_sync()
    assert "user_id" not in api.sent[0]  # nothing to claim it with: behaves as before


# --- the window ------------------------------------------------------------------------


def test_the_sync_cycle_tells_the_user_when_bills_are_held_for_someone_else(
    qapp, monkeypatch
):
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    monkeypatch.setattr(w._sync_service, "is_online", lambda: True)
    monkeypatch.setattr(
        w._sync_service, "push_sync", lambda: {"pushed": 0, "failed": 0, "held": 2}
    )
    monkeypatch.setattr(w._sync_service, "pull_sync", lambda: {})
    w._run_sync_cycle()
    msg = w.statusBar().currentMessage()
    assert "2 bills" in msg and "other users" in msg and "sign in" in msg


def test_signing_out_first_hands_the_users_bills_to_the_server(qapp, dialogs, monkeypatch):
    from ui.main_window import MainWindow

    sign_in_as(monkeypatch, ASHA)
    w = MainWindow()
    w._sync_timer.stop()
    seen = {}
    monkeypatch.setattr(w._sync_service, "is_online", lambda: True)

    def push():
        seen["token_at_push"] = Session.get_token()  # still signed in: it is theirs
        return {"pushed": 1, "failed": 0, "held": 0}

    monkeypatch.setattr(w._sync_service, "push_sync", push)
    w._handle_logout()

    assert seen["token_at_push"] and Session.get_token() is None


def test_signing_out_still_works_when_the_server_is_unreachable(qapp, dialogs, monkeypatch):
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()  # conftest: the server refuses connections
    w._handle_logout()
    assert Session.get_token() is None and w._login_window.isVisible()


def test_a_401_while_signing_out_does_not_pop_the_expired_dialog_too(
    qapp, dialogs, monkeypatch
):
    from services.api_client import SessionExpiredError
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    monkeypatch.setattr(w._sync_service, "is_online", lambda: True)

    def expired():
        w.session_expired.emit()  # what the 401 hook does
        raise SessionExpiredError()

    monkeypatch.setattr(w._sync_service, "push_sync", expired)
    w._handle_logout()

    assert [d[1] for d in dialogs].count("Signed out") == 0
    assert Session.get_token() is None
