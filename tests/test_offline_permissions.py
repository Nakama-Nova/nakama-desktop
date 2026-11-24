"""A restart with no server keeps what the person could do, instead of dropping a custom role to nothing."""

import base64
import json

import pytest
import requests

from services.api_client import APIError
from services.session import Session, _permissions_cache_path

ME = {"role": "cashier-plus", "allowed": ["sales:sale:create", "customers:*"], "by_plant_unit": {}}


def token_for(user: str) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{seg({'alg': 'HS256'})}.{seg({'sub': user, 'exp': 9999999999})}.sig"


class Api:
    def __init__(self, me=None, error=None):
        self.me, self.error = me, error

    def get_my_permissions(self, token):
        if self.error:
            raise self.error
        return self.me


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(Session, "_token", token_for("user-1"))
    monkeypatch.setattr(Session, "_allowed", None)
    monkeypatch.setattr(Session, "_by_plant_unit", {})
    monkeypatch.setattr(Session, "_role", "cashier-plus")


def test_what_the_server_said_is_kept_for_next_time(signed_in):
    Session.refresh_permissions(Api(me=ME))
    saved = json.loads(_permissions_cache_path().read_text())
    assert saved["user"] == "user-1" and saved["me"]["allowed"] == ME["allowed"]


def test_a_restart_with_no_server_uses_the_kept_permissions(signed_in, monkeypatch):
    Session.refresh_permissions(Api(me=ME))
    monkeypatch.setattr(Session, "_allowed", None)  # a fresh start knows nothing yet
    Session.refresh_permissions(Api(error=requests.ConnectionError("down")))
    assert Session.can("sales:sale:create") and Session.can("customers:buyer:read")
    assert not Session.can("payroll:payment:create")


def test_without_a_kept_copy_an_unreachable_server_changes_nothing(signed_in):
    Session.refresh_permissions(Api(error=requests.ConnectionError("down")))
    assert Session._allowed is None  # the built-in table still answers, as before


def test_another_persons_kept_permissions_are_never_used(signed_in, monkeypatch):
    Session.refresh_permissions(Api(me=ME))
    monkeypatch.setattr(Session, "_token", token_for("user-2"))
    monkeypatch.setattr(Session, "_allowed", None)
    Session.refresh_permissions(Api(error=requests.ConnectionError("down")))
    assert Session._allowed is None


def test_a_reachable_server_always_wins_over_the_kept_copy(signed_in):
    Session.refresh_permissions(Api(me=ME))
    Session.refresh_permissions(Api(me={"role": "cashier-plus", "allowed": ["sales:sale:read"], "by_plant_unit": {}}))
    assert Session.can("sales:sale:read") and not Session.can("sales:sale:create")
    assert json.loads(_permissions_cache_path().read_text())["me"]["allowed"] == ["sales:sale:read"]


def test_an_old_server_is_not_a_reason_to_use_the_kept_copy(signed_in, monkeypatch):
    Session.refresh_permissions(Api(me=ME))
    monkeypatch.setattr(Session, "_allowed", None)
    Session.refresh_permissions(Api(error=APIError(500, "boom")))
    assert Session._allowed is None  # only "cannot reach the server" brings the copy back


def test_a_damaged_kept_copy_is_ignored(signed_in):
    path = _permissions_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    Session.refresh_permissions(Api(error=requests.ConnectionError("down")))
    assert Session._allowed is None


def test_nothing_is_kept_when_the_person_is_unknown(monkeypatch):
    monkeypatch.setattr(Session, "_token", "not-a-jwt")
    monkeypatch.setattr(Session, "_allowed", None)
    Session.refresh_permissions(Api(me=ME))
    assert not _permissions_cache_path().exists()
