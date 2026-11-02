"""Forgot password: email a code, then choose a password with it. Remember me lives in
test_session_expiry.py."""

import pytest
import requests

from services.api_client import APIClient, APIError
from ui.forgot_password_dialog import ForgotPasswordDialog, code_problem
from ui.login_window import LoginWindow
from ui.workers import wait_for_jobs

from tests.conftest import settle


class FakeAPI:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def forgot_password(self, email):
        self.calls.append(("forgot", email))
        if self.fail:
            raise self.fail
        return {"message": "ok"}

    def set_password_with_code(self, email, code, new):
        self.calls.append(("set", email, code, new))
        if self.fail:
            raise self.fail
        return {"message": "ok"}


def test_the_form_rules():
    assert "email" in code_problem("nope", "ABCD2345", "LongEnough1", "LongEnough1")
    assert "code" in code_problem("a@x.com", "12", "LongEnough1", "LongEnough1")
    assert "8 characters" in code_problem("a@x.com", "ABCD2345", "short", "short")
    assert "match" in code_problem("a@x.com", "ABCD2345", "LongEnough1", "Different12")
    assert code_problem("a@x.com", "ABCD2345", "LongEnough1", "LongEnough1") is None


def test_asking_for_a_code_then_setting_the_password(qapp):
    api = FakeAPI()
    d = ForgotPasswordDialog(None, api=api)
    d.ask_email.setText("asha@x.com")
    d.send_code()
    settle()
    assert api.calls == [("forgot", "asha@x.com")]
    assert d.stack.currentIndex() == 1 and d.email.text() == "asha@x.com"
    assert "code is on its way" in d.message.text()  # same words whether or not the account exists

    d.code.setText("ABCD2345")
    d.new.setText("LongEnough1")
    d.repeat.setText("LongEnough1")
    d.set_password()
    settle()
    assert api.calls[-1] == ("set", "asha@x.com", "ABCD2345", "LongEnough1")
    assert d.result() == 1  # accepted


def test_a_bad_code_is_explained_in_the_dialog_not_lost(qapp):
    api = FakeAPI(fail=APIError(400, '{"detail": "That code is wrong or has expired. Ask for a new one."}'))
    d = ForgotPasswordDialog(None, email="asha@x.com", api=api, have_code=True)
    d.code.setText("WRONG123")
    d.new.setText("LongEnough1")
    d.repeat.setText("LongEnough1")
    d.set_password()
    settle()
    assert "wrong or has expired" in d.message.text()
    assert d.result() == 0 and d.set_btn.isEnabled()  # can try again


def test_no_connection_is_said_plainly(qapp):
    d = ForgotPasswordDialog(None, api=FakeAPI(fail=requests.ConnectionError("down")))
    d.ask_email.setText("asha@x.com")
    d.send_code()
    settle()
    assert "Cannot reach the server" in d.message.text()


def test_the_sign_in_screen_offers_forgot_password(qapp, monkeypatch):
    seen = []
    monkeypatch.setattr(ForgotPasswordDialog, "exec", lambda self: seen.append(self.ask_email.text()) or 1)
    box = LoginWindow()
    box.username.setText("asha@x.com")
    box.forgot.click()
    assert seen == ["asha@x.com"]  # an email typed as the username is carried over
    assert "Sign in with your new password" in box.error_lbl.text()


def test_the_client_calls_the_two_open_endpoints(monkeypatch):
    import services.api_client as api_client

    seen = []

    class Resp:
        status_code, text = 200, "{}"

        def json(self):
            return {"message": "ok"}

    monkeypatch.setattr(api_client._http, "post", lambda url, **kw: seen.append((url, kw.get("json"))) or Resp())
    api = APIClient("http://x")
    api.forgot_password("a@x.com")
    api.set_password_with_code("a@x.com", "ABCD2345", "LongEnough1")
    assert seen == [
        ("http://x/auth/password/forgot", {"email": "a@x.com"}),
        ("http://x/auth/password/set", {"email": "a@x.com", "code": "ABCD2345", "new_password": "LongEnough1"}),
    ]
