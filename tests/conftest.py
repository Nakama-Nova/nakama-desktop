"""
Desktop tests run the real Qt widgets headless (offscreen) with the backend
unreachable, in a temp working directory, with the OS keyring disabled, so they
never touch real data, saved logins or a running server.
"""

import os
import pathlib
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# Port 9 (discard) refuses at once, so "offline" is instant and deterministic.
# Set before the app imports api_client, which reads it at import time.
os.environ["API_BASE_URL"] = "http://127.0.0.1:9"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """data/ (outbox, item cache) lands in tmp_path; no keyring; logged-in owner."""
    monkeypatch.chdir(tmp_path)
    import services.session as sess
    from services.enums import UserRole

    monkeypatch.setattr(sess, "_keyring", lambda: None)
    monkeypatch.setattr(sess.Session, "_token", "test-token")
    monkeypatch.setattr(sess.Session, "_role", UserRole.OWNER)
    import services.api_client as api

    monkeypatch.setattr(api, "_down_until", 0.0)  # no "server is down" carried between tests
    from ui.notifier import Notifier

    monkeypatch.setattr(Notifier, "AUTOSTART", False)  # tests never poll a server in the background
    yield


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    """Record QMessageBox pop-ups instead of blocking on them."""
    from PyQt6.QtWidgets import QMessageBox

    seen = []

    def make(kind):
        def show(parent, title, text, *a, **k):
            seen.append((kind, title, text))
            return QMessageBox.StandardButton.Yes

        return staticmethod(show)

    for kind in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QMessageBox, kind, make(kind))
    return seen
