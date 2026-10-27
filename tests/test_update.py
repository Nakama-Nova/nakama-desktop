"""Update notifications: asking the server for a newer release, checking the download, the banner."""

import hashlib

import pytest
import requests

from services import update_service as svc
from services.api_client import APIError, ForbiddenError
from services.update_service import UpdateError, UpdateInfo
from services.version import is_release_build, parse_version
from ui.updater import UpdateBanner, Updater

NAME = "VrikshaStudiosDesk-Setup-1.2.0.exe"
BODY = b"installer-bytes"
SUM = hashlib.sha256(BODY).hexdigest()


def latest(version="1.2.0", **over):
    return {"version": version, "notes": "Faster stock screen", "installer_name": NAME, "size": 10, "sha256": SUM, **over}


class FakeApi:
    """Stands in for APIClient: returns data or raises what the server would."""

    _base_url = "https://shop.test"

    def __init__(self, data=None, error=None):
        self.data, self.error, self.asked = data, error, []

    def _get(self, path, token, params=None, quiet=False):
        self.asked.append((path, token, quiet))
        if self.error:
            raise self.error
        return self.data


class Resp:
    def __init__(self, status=200, chunks=(), headers=None):
        self.status_code, self._chunks, self.headers = status, chunks, headers or {}

    def iter_content(self, chunk_size=0):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def info():
    return UpdateInfo("1.2.0", "notes", NAME, SUM, 10)


# ---------------------------------------------------------------- versions
def test_versions_parse_and_compare():
    assert parse_version("v1.2.3") == (1, 2, 3) and parse_version("1.10.0") == (1, 10, 0)
    assert parse_version("0.0.0-dev") is None and parse_version("v1.2") is None and parse_version(None) is None
    assert parse_version("1.10.0") > parse_version("1.9.9")  # numbers, not text


def test_running_from_source_is_never_a_release_build():
    assert is_release_build() is False


# ---------------------------------------------------------------- the check
def test_a_newer_version_is_reported_and_the_signed_in_token_is_used(monkeypatch):
    monkeypatch.setattr(svc.Session, "_token", "staff-token")
    api = FakeApi(latest())
    got = svc.check_for_update("1.0.0", api=api)
    assert got.version == "1.2.0" and got.installer_name == NAME and got.sha256 == SUM
    assert got.notes == "Faster stock screen"
    assert api.asked == [("/app/updates/latest", "staff-token", True)]


@pytest.mark.parametrize("current", ["1.2.0", "1.3.0", "2.0.0"])
def test_same_or_newer_is_not_an_update(current):
    assert svc.check_for_update(current, api=FakeApi(latest())) is None


def test_a_development_build_never_asks_or_prompts():
    api = FakeApi(latest())
    assert svc.check_for_update("0.0.0-dev", api=api) is None
    assert api.asked == []


def test_nothing_published_yet_is_not_an_error():
    assert svc.check_for_update("1.0.0", api=FakeApi(error=APIError(404, "{}"))) is None


@pytest.mark.parametrize(
    "error,words",
    [
        (APIError(401, "{}"), "Sign in again"),
        (ForbiddenError(403, "no"), "not allowed"),
        (APIError(503, '{"detail": "Updates are not set up on this server yet"}'), "not set up"),
        (APIError(502, '{"detail": "The update token was refused (it may have expired)"}'), "token was refused"),
        (requests.ConnectionError(), "Could not reach"),
    ],
)
def test_check_failures_are_plain_messages(error, words):
    with pytest.raises(UpdateError, match=words):
        svc.check_for_update("1.0.0", api=FakeApi(error=error))


@pytest.mark.parametrize(
    "bad",
    [{"installer_name": "evil.exe"}, {"installer_name": "../../x.exe"}, {"sha256": "nothex"}, {"sha256": ""}],
)
def test_a_strange_answer_from_the_server_is_not_trusted(bad):
    with pytest.raises(UpdateError, match="does not look right"):
        svc.check_for_update("1.0.0", api=FakeApi(latest(**bad)))


# ---------------------------------------------------------------- the download
def getter(seen, status=200, body=BODY):
    def get(url, headers=None, stream=False, timeout=None):
        seen.update(url=url, headers=headers)
        return Resp(status, [body[:5], body[5:]], {"Content-Length": str(len(body))})

    return get


def test_a_good_download_goes_to_the_server_with_the_login_and_is_verified(tmp_path):
    seen, progress = {}, []
    path = svc.download_installer(
        info(), progress=lambda d, t: progress.append((d, t)), get=getter(seen),
        folder=str(tmp_path), base_url="https://shop.test/", token="staff-token",
    )
    assert open(path, "rb").read() == BODY and progress[-1] == (15, 15)
    assert seen["url"] == "https://shop.test/app/updates/download/1.2.0"
    assert seen["headers"] == {"Authorization": "Bearer staff-token"}


def test_a_download_that_does_not_match_its_checksum_is_deleted(tmp_path):
    with pytest.raises(UpdateError, match="damaged"):
        svc.download_installer(info(), get=getter({}, body=b"tampered-bytes!"), folder=str(tmp_path), base_url="https://s", token="t")
    assert list(tmp_path.iterdir()) == []  # nothing left to run by accident


def test_cancelling_stops_and_cleans_up(tmp_path):
    with pytest.raises(UpdateError, match="cancelled"):
        svc.download_installer(info(), cancelled=lambda: True, get=getter({}), folder=str(tmp_path), base_url="https://s", token="t")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("status,words", [(401, "Sign in again"), (404, "404"), (502, "502")])
def test_download_refusals_are_plain_messages(tmp_path, status, words):
    with pytest.raises(UpdateError, match=words):
        svc.download_installer(info(), get=getter({}, status=status), folder=str(tmp_path), base_url="https://s", token="t")


def test_an_interrupted_download_is_cleaned_up(tmp_path):
    def get(*a, **k):
        raise requests.ConnectionError()

    with pytest.raises(UpdateError, match="interrupted"):
        svc.download_installer(info(), get=get, folder=str(tmp_path), base_url="https://s", token="t")


def test_the_installer_is_started_silently_and_per_user():
    started = {}
    svc.launch_installer(r"C:\tmp\setup.exe", popen=lambda args, **kw: started.update(args=args))
    assert started["args"][0] == r"C:\tmp\setup.exe"
    assert "/SILENT" in started["args"] and "/CLOSEAPPLICATIONS" in started["args"]


# ---------------------------------------------------------------- the banner
def test_banner_shows_the_new_version_and_hides_on_later(qapp):
    banner = UpdateBanner()
    assert banner.isHidden()
    banner.show_update(info())
    assert not banner.isHidden() and "1.2.0" in banner.text.text()
    assert banner.text.toolTip() == "notes"


def test_updater_shows_the_banner_when_a_newer_version_is_found(qapp):
    from PyQt6.QtWidgets import QWidget

    banner = UpdateBanner()
    up = Updater(QWidget(), banner, quit_app=lambda: None)
    up._checked(info(), "", manual=False)
    assert not banner.isHidden()
    banner.hide()
    up._checked(None, "", manual=False)  # nothing new: stays quiet
    assert banner.isHidden()


def test_updater_does_not_start_checks_when_running_from_source(qapp):
    from PyQt6.QtWidgets import QWidget

    up = Updater(QWidget(), UpdateBanner(), quit_app=lambda: None)
    up.start()
    assert not up._timer.isActive()
