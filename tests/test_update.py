"""Update notifications: finding a newer release, checking the download, the banner."""

import hashlib

import pytest
import requests

from services import update_service as svc
from services.update_service import UpdateError, UpdateInfo
from services.version import is_release_build, parse_version
from ui.updater import UpdateBanner, Updater

BASE = "https://github.com/Nakama-Nova/nakama-desktop/releases/download/v1.2.0/"
NAME = "VrikshaStudiosDesk-Setup-1.2.0.exe"


def release(tag="v1.2.0", assets=None, body="Faster stock screen"):
    if assets is None:
        assets = [
            {"name": NAME, "browser_download_url": BASE + NAME, "size": 10},
            {"name": NAME + ".sha256", "browser_download_url": BASE + NAME + ".sha256", "size": 100},
        ]
    return {"tag_name": tag, "body": body, "assets": assets}


class Resp:
    def __init__(self, status=200, data=None, text="", chunks=(), headers=None):
        self.status_code, self._data, self.text = status, data, text
        self._chunks, self.headers = chunks, headers or {}

    def json(self):
        return self._data

    def iter_content(self, chunk_size=0):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def getter(resp):
    return lambda url, **kw: resp


def info():
    return UpdateInfo("1.2.0", "notes", BASE + NAME, NAME, BASE + NAME + ".sha256", 10)


# ---------------------------------------------------------------- versions
def test_versions_parse_and_compare():
    assert parse_version("v1.2.3") == (1, 2, 3) and parse_version("1.10.0") == (1, 10, 0)
    assert parse_version("0.0.0-dev") is None and parse_version("v1.2") is None and parse_version(None) is None
    assert parse_version("1.10.0") > parse_version("1.9.9")  # numbers, not text


def test_running_from_source_is_never_a_release_build():
    assert is_release_build() is False


# ---------------------------------------------------------------- the check
def test_a_newer_release_is_reported_with_its_installer():
    got = svc.check_for_update("1.0.0", get=getter(Resp(data=release())))
    assert got.version == "1.2.0" and got.installer_name == NAME and got.notes == "Faster stock screen"
    assert got.sha256_url.endswith(".sha256")


@pytest.mark.parametrize("current", ["1.2.0", "1.3.0", "2.0.0"])
def test_same_or_newer_is_not_an_update(current):
    assert svc.check_for_update(current, get=getter(Resp(data=release()))) is None


def test_a_development_build_is_never_prompted():
    assert svc.check_for_update("0.0.0-dev", get=getter(Resp(data=release()))) is None


def test_a_release_without_the_installer_files_is_ignored():
    assert svc.check_for_update("1.0.0", get=getter(Resp(data=release(assets=[])))) is None
    only_exe = [{"name": NAME, "browser_download_url": BASE + NAME, "size": 1}]
    assert svc.check_for_update("1.0.0", get=getter(Resp(data=release(assets=only_exe)))) is None


def test_downloads_from_anywhere_but_the_projects_releases_are_refused():
    evil = "https://evil.example.com/" + NAME
    assets = [
        {"name": NAME, "browser_download_url": evil, "size": 1},
        {"name": NAME + ".sha256", "browser_download_url": BASE + NAME + ".sha256", "size": 1},
    ]
    with pytest.raises(UpdateError, match="unexpected"):
        svc.check_for_update("1.0.0", get=getter(Resp(data=release(assets=assets))))


def test_check_failures_are_plain_errors_not_crashes():
    def offline(url, **kw):
        raise requests.ConnectionError()

    with pytest.raises(UpdateError, match="Could not reach"):
        svc.check_for_update("1.0.0", get=offline)
    with pytest.raises(UpdateError, match="403"):
        svc.check_for_update("1.0.0", get=getter(Resp(status=403)))
    assert svc.check_for_update("1.0.0", get=getter(Resp(status=404))) is None  # nothing published yet


# ---------------------------------------------------------------- the download
def download(tmp_path, body=b"installer-bytes", digest=None, **over):
    digest = digest or hashlib.sha256(body).hexdigest()
    sums = f"{digest}  {NAME}\n"

    def get(url, **kw):
        if url.endswith(".sha256"):
            return Resp(text=sums)
        return Resp(chunks=[body[:5], body[5:]], headers={"Content-Length": str(len(body))}, **over)

    return get


def test_a_good_download_is_saved_and_reports_progress(tmp_path):
    seen = []
    path = svc.download_installer(info(), progress=lambda d, t: seen.append((d, t)), get=download(tmp_path), folder=str(tmp_path))
    assert open(path, "rb").read() == b"installer-bytes"
    assert seen[-1] == (15, 15)


def test_a_download_that_does_not_match_its_checksum_is_deleted(tmp_path):
    with pytest.raises(UpdateError, match="damaged"):
        svc.download_installer(info(), get=download(tmp_path, digest="0" * 64), folder=str(tmp_path))
    assert list(tmp_path.iterdir()) == []  # nothing left to run by accident


def test_cancelling_stops_and_cleans_up(tmp_path):
    with pytest.raises(UpdateError, match="cancelled"):
        svc.download_installer(info(), cancelled=lambda: True, get=download(tmp_path), folder=str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_an_unreadable_checksum_means_nothing_is_installed(tmp_path):
    def get(url, **kw):
        return Resp(text="not a checksum")

    with pytest.raises(UpdateError, match="checksum"):
        svc.download_installer(info(), get=get, folder=str(tmp_path))


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

    window = QWidget()
    banner = UpdateBanner()
    up = Updater(window, banner, quit_app=lambda: None)
    up._checked(info(), "", manual=False)
    assert not banner.isHidden()
    banner.hide()
    up._checked(None, "", manual=False)  # nothing new: stays quiet
    assert banner.isHidden()


def test_updater_does_not_start_checks_when_running_from_source(qapp, monkeypatch):
    from PyQt6.QtWidgets import QWidget

    up = Updater(QWidget(), UpdateBanner(), quit_app=lambda: None)
    up.start()
    assert not up._timer.isActive()
