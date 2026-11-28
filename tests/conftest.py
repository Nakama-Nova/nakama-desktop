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


def settle():
    """Let the screens' background loads finish and deliver their rows to the window."""
    import time

    from PyQt6.QtCore import QCoreApplication

    from ui import workers

    workers.wait_for_jobs()
    for _ in range(100):
        QCoreApplication.processEvents()
        if workers._pending == 0:
            break
        time.sleep(0.01)


@pytest.fixture(autouse=True)
def finish_background_jobs():
    """Screens load in the background: let every job end before the next test (and before the
    Qt application is destroyed), so none answers into a window that is gone."""
    yield
    from ui.workers import wait_for_jobs

    wait_for_jobs()


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


def create_bill(screen, seconds: float = 10.0) -> str:
    """Press Create bill and wait for it to finish (it runs on a worker thread); returns how it ended."""
    import time

    from PyQt6.QtCore import QCoreApplication

    ended = []
    screen.bill_finished.connect(ended.append)
    screen._generate_invoice()
    deadline = time.monotonic() + seconds
    while screen._bill_in_flight and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    screen.bill_finished.disconnect(ended.append)
    return ended[-1] if ended else "not-started"  # validation stops (missing phone, ...) never start a bill
