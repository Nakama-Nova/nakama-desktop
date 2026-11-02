"""Talks to a real backend, so it is skipped unless you point it at one:

    NAKAMA_TEST_URL=http://127.0.0.1:8000 NAKAMA_TEST_USER=owner NAKAMA_TEST_PASS=... pytest tests/test_backend_live.py

Use a development or staging server, never the shop's live one. Everything here only reads.
"""

import os

import pytest

from services.api_client import APIClient, ForbiddenError, SessionExpiredError, reset_session_expired
from services.places_service import PlacesService
from services.registers_service import RegistersService
from services.session import Session

URL = os.getenv("NAKAMA_TEST_URL")
USER, PASSWORD = os.getenv("NAKAMA_TEST_USER"), os.getenv("NAKAMA_TEST_PASS")

pytestmark = pytest.mark.skipif(not (URL and USER and PASSWORD), reason="set NAKAMA_TEST_URL, _USER and _PASS")


@pytest.fixture(scope="module")
def api():
    return APIClient(URL)


@pytest.fixture(scope="module")
def signed_in(api):
    login = api.login(USER, PASSWORD)
    assert login and login.get("access_token"), "login failed: wrong test user or password"
    Session.set_token(login["access_token"])
    yield login
    Session.clear_token()


def test_the_server_answers_its_health_check(api):
    assert api.health_check()


def test_a_wrong_password_is_none_not_an_error(api):
    assert api.login(USER, PASSWORD + "-wrong") is None


def test_a_bad_token_is_a_session_expiry(api):
    with pytest.raises(SessionExpiredError):
        api._get("/auth/me", "not-a-token")
    reset_session_expired()


def test_the_signed_in_user_can_be_read(api, signed_in):
    me = api._get("/auth/me", signed_in["access_token"])
    assert me["username"] == USER


def test_items_and_places_come_back_in_the_shape_the_screens_read(api, signed_in):
    items = api.get_items(signed_in["access_token"])
    assert isinstance(items, list)
    for item in items[:5]:
        assert {"id", "name", "selling_price"} <= item.keys()
    try:
        places = PlacesService(api).places()
    except ForbiddenError:
        pytest.skip("this test user may not see places")
    assert all({"id", "name", "kind"} <= p.keys() for p in places)


def test_budgets_and_machines_are_lists_for_a_permitted_user(api, signed_in):
    try:
        assert isinstance(RegistersService(api).machines(), list)
        assert isinstance(RegistersService(api).current_budgets(), list)
    except ForbiddenError:
        pytest.skip("this test user may not see machines or budgets")
