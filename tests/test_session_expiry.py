"""
A rejected login (401) is handled once, in one place, and never strands the user:
they are told, returned to sign-in, and their queued offline bills are kept. Signing
in or restoring a session also copes with an unreachable server.
"""

import base64
import json
import time
from types import SimpleNamespace

import pytest
import requests

import services.api_client as api_client
import services.session as sess
from database.outbox_repository import OutboxRepository
from services.api_client import (
    APIClient,
    APIError,
    SessionExpiredError,
    set_session_expired_hook,
)
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.session import Session
from ui.login_window import LoginWindow
from ui.main_window import MainWindow


class Resp:
    def __init__(self, status, body="", content=b""):
        self.status_code, self.text, self.content = status, body, content

    def json(self):
        return json.loads(self.text)


def _answer(monkeypatch, status, body='{"detail": "Could not validate credentials"}'):
    resp = Resp(status, body)
    for verb in ("get", "post", "put", "patch", "delete"):
        monkeypatch.setattr(api_client._http, verb, lambda *a, **k: resp)


@pytest.fixture(autouse=True)
def no_hook_leaks():
    set_session_expired_hook(None)
    yield
    set_session_expired_hook(None)


# --- the API client ----------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c._get("/x", "t"),
        lambda c: c._post("/x", "t", json={}),
        lambda c: c._put("/x", "t", json={}),
        lambda c: c._patch("/x", "t"),
        lambda c: c._delete("/x", "t"),
        lambda c: c._get_bytes("/x", "t"),
    ],
)
def test_every_verb_turns_a_401_into_session_expired(monkeypatch, call):
    _answer(monkeypatch, 401)
    with pytest.raises(SessionExpiredError) as e:
        call(APIClient())
    assert e.value.status_code == 401 and e.value.reported  # no second pop-up


def test_background_calls_report_expiry_instead_of_looking_offline(monkeypatch):
    """Sync used to treat a 401 like 'server unreachable' and stall silently."""
    _answer(monkeypatch, 401)
    fired = []
    set_session_expired_hook(lambda: fired.append(1))
    with pytest.raises(SessionExpiredError):
        APIClient().push_sync("t", [])
    with pytest.raises(SessionExpiredError):
        APIClient().pull_sync("t", "1970-01-01T00:00:00+00:00")
    assert fired == [1]  # told once, not once per call


def test_expiry_is_not_swallowed_by_except_apierror_fallbacks(monkeypatch):
    """get_items() and friends return None on APIError; a 401 must not look like that."""
    _answer(monkeypatch, 401)
    assert not issubclass(SessionExpiredError, APIError)
    with pytest.raises(SessionExpiredError):
        APIClient().get_items("t")
    with pytest.raises(SessionExpiredError):
        APIClient().create_sale("t", [])


def test_the_global_exception_hook_ignores_it_and_still_reports_real_errors(
    qapp, dialogs
):
    import main

    err = SessionExpiredError()
    main.exception_hook(type(err), err, None)
    assert dialogs == []  # no "Server Error" box on top of the sign-in prompt
    api_err = APIError(500, "boom")
    main.exception_hook(type(api_err), api_err, None)
    assert [d[0] for d in dialogs] == ["critical"]  # real errors still reach the user


def test_hook_fires_once_per_sign_in(monkeypatch):
    _answer(monkeypatch, 401)
    fired = []
    set_session_expired_hook(lambda: fired.append(1))
    for _ in range(3):
        with pytest.raises(SessionExpiredError):
            APIClient()._get("/x", "t")
    assert fired == [1]
    api_client.reset_session_expired()  # what a fresh sign-in does
    with pytest.raises(SessionExpiredError):
        APIClient()._get("/x", "t")
    assert fired == [1, 1]


def test_other_errors_are_unchanged(monkeypatch):
    fired = []
    set_session_expired_hook(lambda: fired.append(1))
    _answer(monkeypatch, 500, "boom")
    with pytest.raises(APIError) as e:
        APIClient()._get("/x", "t", quiet=True)
    assert not isinstance(e.value, SessionExpiredError) and fired == []


# --- the main window reacts ---------------------------------------------------------


def test_expiry_signs_out_once_keeps_the_outbox_and_shows_login(
    qapp, dialogs, monkeypatch
):
    OutboxRepository().add_entry("sale", "create", {"id": "s1"})
    w = MainWindow()
    _answer(monkeypatch, 401)

    for _ in range(2):  # two screens hit the 401 at the same time
        with pytest.raises(SessionExpiredError):
            InventoryService().get_items()

    assert [d[1] for d in dialogs].count("Signed out") == 1
    assert not any("Server Error" in d[1] for d in dialogs)
    assert Session.get_token() is None and Session.get_role() is None
    assert not w._sync_timer.isActive()
    assert w._login_window.isVisible()
    assert len(OutboxRepository().get_pending()) == 1  # the bill is not lost


# --- login ---------------------------------------------------------------------------


def _try_login(qapp):
    w = LoginWindow()
    w.username.setText("alice")
    w.password.setText("pw")
    w.handle_login()  # must not raise
    return w


def test_login_with_server_unreachable_explains_and_unfreezes_the_button(qapp):
    w = _try_login(qapp)  # conftest points the app at a port that refuses
    assert w.button.isEnabled() and w.button.text() == "Sign In"
    assert "Can't reach the server" in w.error_lbl.text()


def test_login_timeout_is_handled_too(qapp, monkeypatch):
    def slow(*a, **k):
        assert k["timeout"] == api_client.LOGIN_TIMEOUT  # never waits forever
        raise requests.Timeout()

    monkeypatch.setattr(api_client._http, "post", slow)
    w = _try_login(qapp)
    assert w.button.isEnabled() and "Can't reach" in w.error_lbl.text()


def test_login_with_wrong_password_still_says_so(qapp, monkeypatch):
    _answer(monkeypatch, 401, '{"detail": "Invalid credentials"}')
    w = _try_login(qapp)
    assert w.button.isEnabled()
    assert "Invalid username or password" in w.error_lbl.text()


def test_login_when_the_server_is_broken_says_so_not_wrong_password(qapp, monkeypatch):
    _answer(monkeypatch, 500, "Internal Server Error")
    w = _try_login(qapp)
    assert w.button.isEnabled()
    assert "server had a problem (500)" in w.error_lbl.text()
    assert "Invalid" not in w.error_lbl.text()


# --- restoring a saved session at start-up -----------------------------------------


class FakeKeyring:
    """In-memory stand-in for the OS credential store."""

    def __init__(self, **stored):
        self.data = {("NakamaDesk", k): v for k, v in stored.items()}
        self.errors = SimpleNamespace(PasswordDeleteError=KeyError)

    def get_password(self, service, key):
        return self.data.get((service, key))

    def set_password(self, service, key, value):
        self.data[(service, key)] = value

    def delete_password(self, service, key):
        del self.data[(service, key)]


def _token(exp):
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{seg({'alg': 'HS256'})}.{seg({'sub': 'u', 'exp': exp})}.sig"


def _restore(monkeypatch, kr, **kw):
    monkeypatch.setattr(sess, "_keyring", lambda: kr)
    monkeypatch.setattr(Session, "_token", None)
    monkeypatch.setattr(Session, "_role", None)
    return Session.restore(**kw)


def test_a_valid_saved_login_is_restored(monkeypatch):
    kr = FakeKeyring(auth_token=_token(time.time() + 600), auth_role="sales")
    assert _restore(monkeypatch, kr)
    assert Session.get_role() == UserRole.SALES and Session.get_token()


def test_an_expired_login_is_discarded_when_the_server_is_reachable(monkeypatch):
    kr = FakeKeyring(auth_token=_token(time.time() - 60), auth_role="sales")
    assert not _restore(monkeypatch, kr, allow_expired=lambda: False)
    assert Session.get_token() is None and kr.data == {}  # wiped, as before


def test_an_expired_login_is_discarded_without_the_offline_hook(monkeypatch):
    kr = FakeKeyring(auth_token=_token(time.time() - 60), auth_role="sales")
    assert not _restore(monkeypatch, kr)
    assert kr.data == {}


def test_an_expired_login_is_kept_when_the_server_is_down_so_the_counter_can_bill(
    monkeypatch,
):
    stale = _token(time.time() - 3600)
    kr = FakeKeyring(auth_token=stale, auth_role="sales")
    assert _restore(monkeypatch, kr, allow_expired=lambda: True)
    assert Session.get_role() == UserRole.SALES and Session.get_token() == stale
    assert kr.get_password("NakamaDesk", "auth_token") == stale  # still saved


def test_an_expired_login_without_a_known_role_is_not_restored_offline(monkeypatch):
    kr = FakeKeyring(auth_token=_token(time.time() - 60))
    assert not _restore(monkeypatch, kr, allow_expired=lambda: True)
    assert Session.get_token() is None


def test_the_offline_check_is_only_made_when_the_token_is_expired(monkeypatch):
    kr = FakeKeyring(auth_token=_token(time.time() + 600), auth_role="owner")
    asked = []
    assert _restore(monkeypatch, kr, allow_expired=lambda: asked.append(1) or False)
    assert asked == []  # no needless network check at every start
