"""Hardening: every request has a timeout, a lockout is explained, plain http is flagged."""

import pytest
import requests

from services import api_client
from services.api_client import APIClient, APIError, insecure_remote


class Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text
        self.content = b"pdf"

    def json(self):
        return self._data if self._data is not None else {}


@pytest.fixture
def seen(monkeypatch):
    """Record the timeout each HTTP call is made with."""
    calls = {}

    def make(name):
        def fake(url, **kw):
            calls[name] = kw.get("timeout")
            return Resp(200, {}, "")

        return fake

    for m in ("get", "post", "put", "patch", "delete"):
        monkeypatch.setattr(api_client._http, m, make(m))
    return calls


def test_every_kind_of_call_has_a_timeout(seen, tmp_path):
    api = APIClient("http://x")
    api._get("/a", "t")
    api._post("/a", "t", json={})
    api._put("/a", "t", json={})
    api._patch("/a", "t", json={})
    api._delete("/a", "t")
    api.login("u", "p")
    assert seen["get"] == api_client.REQUEST_TIMEOUT
    assert seen["post"] == api_client.REQUEST_TIMEOUT  # the last post is the login
    for kind in ("put", "patch", "delete"):
        assert seen[kind] == api_client.REQUEST_TIMEOUT
    photo = tmp_path / "a.png"
    photo.write_bytes(b"x")
    api._upload("/up", "t", str(photo))
    assert seen["post"] == api_client.UPLOAD_TIMEOUT
    api._get_bytes("/pdf", "t")
    assert seen["get"] == api_client.UPLOAD_TIMEOUT


def test_there_is_no_bare_request_left_in_the_client():
    import ast

    tree = ast.parse(open(api_client.__file__, encoding="utf-8").read())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "requests"
        and n.func.attr in ("get", "post", "put", "patch", "delete")
    ]
    assert not calls, "go through _send so the shared connection and fail-fast apply"
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_send"
    ]
    assert len(calls) >= 9
    assert all("timeout" in [k.arg for k in c.keywords] for c in calls), "a request has no timeout"


def test_too_many_wrong_passwords_is_explained_not_called_a_wrong_password(monkeypatch):
    monkeypatch.setattr(
        api_client._http,
        "post",
        lambda url, **kw: Resp(429, text='{"detail": "Too many failed sign-in attempts. Try again in 15 minutes."}'),
    )
    with pytest.raises(APIError, match="Too many failed sign-in attempts"):
        APIClient("http://x").login("asha", "guess")


def test_a_wrong_password_is_still_just_none(monkeypatch):
    monkeypatch.setattr(api_client._http, "post", lambda url, **kw: Resp(401, text="{}"))
    assert APIClient("http://x").login("asha", "guess") is None


def test_the_login_window_shows_the_lockout_and_offline_messages(qapp, monkeypatch):
    from ui.login_window import LoginWindow

    w = LoginWindow()
    w.username.setText("asha")
    w.password.setText("guess")

    monkeypatch.setattr(w._auth, "login", lambda u, p: (_ for _ in ()).throw(APIError(429, '{"detail": "Too many failed sign-in attempts."}')))
    w.handle_login()
    assert "Too many failed" in w.error_lbl.text() and w.button.isEnabled()

    monkeypatch.setattr(w._auth, "login", lambda u, p: (_ for _ in ()).throw(requests.ConnectionError()))
    w.handle_login()
    assert "Cannot reach the server" in w.error_lbl.text() and w.button.isEnabled()


@pytest.mark.parametrize(
    "url,insecure",
    [
        ("https://shop.example.com", False),
        ("http://127.0.0.1:8000", False),
        ("http://localhost:8000", False),
        ("http://192.168.1.20:8000", False),
        ("http://10.0.0.5:8000", False),
        ("http://172.20.1.1:8000", False),
        ("http://shop.local:8000", False),
        ("http://shop.example.com", True),
        ("http://203.0.113.9:8000", True),
        ("http://172.32.0.1", True),  # just outside the private range
    ],
)
def test_plain_http_is_only_ok_on_this_pc_or_the_shop_network(url, insecure):
    assert insecure_remote(url) is insecure


def test_unhandled_network_errors_become_plain_messages(qapp, monkeypatch):
    import main as app_main
    from PyQt6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[1])))
    app_main.exception_hook(requests.Timeout, requests.Timeout(), None)
    app_main.exception_hook(requests.ConnectionError, requests.ConnectionError(), None)
    assert shown == ["Server not answering", "No connection"]
