"""Speed: no server calls while the window is built, shared connection, fail fast when offline."""

import time

import pytest
import requests
from urllib3.exceptions import NewConnectionError

from services import api_client
from services.api_client import APIClient


class Resp:
    status_code = 200
    text = ""

    def json(self):
        return {}


def refused():
    """What requests raises when nothing is listening / the network is down."""
    inner = NewConnectionError(None, "refused")
    return requests.ConnectionError(type("MaxRetry", (), {"reason": inner})())


def test_opening_the_main_window_makes_no_server_call(qapp, monkeypatch):
    calls = []
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: calls.append(url) or Resp())
    monkeypatch.setattr(api_client._http, "post", lambda url, **kw: calls.append(url) or Resp())
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    assert calls == []  # Home fills in a moment later, after the window is shown


def test_every_call_shares_one_connection(monkeypatch):
    used = []
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: used.append("session") or Resp())
    APIClient("http://x")._get("/a", "t")
    APIClient("http://x")._get("/b", "t")  # a different client object, same connection pool
    assert used == ["session", "session"]


def test_after_a_failed_connection_calls_fail_at_once(monkeypatch):
    attempts = []

    def down(url, **kw):
        attempts.append(url)
        raise refused()

    monkeypatch.setattr(api_client._http, "get", down)
    api = APIClient("http://x")
    with pytest.raises(requests.ConnectionError):
        api._get("/a", "t")
    start = time.monotonic()
    for _ in range(5):
        with pytest.raises(requests.ConnectionError):
            api._get("/b", "t")
    assert len(attempts) == 1 and time.monotonic() - start < 0.5  # the other five never left the PC


def test_sign_in_and_health_check_always_try_again(monkeypatch):
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: (_ for _ in ()).throw(refused()))
    api = APIClient("http://x")
    assert api.health_check() is False  # trips the pause
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: Resp())
    assert api.health_check() is True  # server came back: noticed immediately
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: (_ for _ in ()).throw(refused()))
    with pytest.raises(requests.ConnectionError):
        api._get("/a", "t")
    monkeypatch.setattr(api_client._http, "post", lambda url, **kw: Resp())
    assert api.login("u", "p") == {}  # sign-in is never blocked by the pause


@pytest.mark.parametrize(
    "error",
    [
        requests.ReadTimeout("slow server"),
        requests.ConnectionError("Connection aborted."),  # dropped mid-request, not "offline"
    ],
)
def test_a_slow_or_dropped_reply_does_not_start_the_pause(monkeypatch, error):
    calls = []

    def flaky(url, **kw):
        calls.append(url)
        raise error

    monkeypatch.setattr(api_client._http, "get", flaky)
    api = APIClient("http://x")
    for _ in range(2):
        with pytest.raises(requests.RequestException):
            api._get("/a", "t")
    assert len(calls) == 2  # both really tried


def test_the_pause_ends(monkeypatch):
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: (_ for _ in ()).throw(refused()))
    api = APIClient("http://x")
    with pytest.raises(requests.ConnectionError):
        api._get("/a", "t")
    monkeypatch.setattr(api_client, "_down_until", time.monotonic() - 1)  # pause is over
    monkeypatch.setattr(api_client._http, "get", lambda url, **kw: Resp())
    assert api._get("/a", "t") == {}
