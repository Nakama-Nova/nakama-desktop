"""
ui/workers.py

Run slow work (server calls) off the GUI thread, so the window never freezes while it waits.

    run_async(fn, on_result, on_error)   one background job
    load_async(owner, fetch, render)     refresh a screen: fetch() runs in the background,
                                         render(result) runs back on the GUI thread

fetch() must not touch any widget. Whatever it returns (or raises) comes back to the GUI
thread, and only the callbacks there update the UI. A newer load_async on the same owner
makes an older one that is still running a no-op when it finishes.

Server errors that a call would normally show as a dialog are collected while the job runs
and shown on the GUI thread afterwards, so the user still hears why a screen is empty.
"""

import atexit
import logging
import sys

import requests
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, pyqtSignal

from services import api_client

logger = logging.getLogger(__name__)

def wait_for_jobs() -> None:
    """A job still running when the application is destroyed would answer into nothing."""
    pool = QThreadPool.globalInstance()
    if pool is not None:  # None once Qt has been shut down
        pool.waitForDone(5000)


atexit.register(wait_for_jobs)
_hooked = False

_live: set = set()  # keeps each job alive until its result has been delivered
_pending = 0
_busy_listeners: list = []  # called on the GUI thread with True/False when work starts/stops


def on_busy_changed(callback) -> None:
    """callback(is_busy) is called when the first job starts and when the last one ends."""
    _busy_listeners.append(callback)


def _set_pending(delta: int) -> None:
    global _pending
    before = _pending
    _pending = max(0, _pending + delta)
    if (before == 0) != (_pending == 0):
        for callback in list(_busy_listeners):
            try:
                callback(_pending > 0)
            except RuntimeError:  # a listener's widget has been deleted
                _busy_listeners.remove(callback)


class _Signals(QObject):
    reports = pyqtSignal(list)  # server errors the user should be shown
    result = pyqtSignal(object)
    error = pyqtSignal(object)


class _Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.setAutoDelete(False)  # Python owns it until delivery
        self._fn = fn
        self.signals = _Signals()

    def run(self):
        api_client.begin_background()
        try:
            value = self._fn()
        except Exception as exc:  # handed to the GUI thread, never raised here
            self.signals.reports.emit(api_client.end_background())
            self.signals.error.emit(exc)
        else:
            self.signals.reports.emit(api_client.end_background())
            self.signals.result.emit(value)


def _show_reports(errors: list) -> None:
    """Show the server's own reasons ("Not enough stock...") like a foreground call would."""
    for err in errors:
        sys.excepthook(type(err), err, None)
        err.reported = True  # not a second time if it is also raised


def run_async(fn, on_result=None, on_error=None) -> None:
    """Run fn() on a pool thread; call on_result(value) or on_error(exc) on the GUI thread."""
    global _hooked
    app = QCoreApplication.instance()
    if app is not None and not _hooked:
        _hooked = True
        app.aboutToQuit.connect(wait_for_jobs)
    job = _Job(fn)
    _live.add(job)
    _set_pending(+1)

    def finish(callback):
        def deliver(arg):
            _live.discard(job)
            _set_pending(-1)
            if callback is not None:
                callback(arg)

        return deliver

    job.signals.reports.connect(_show_reports)
    job.signals.result.connect(finish(on_result))
    job.signals.error.connect(finish(on_error or _default_error))
    QThreadPool.globalInstance().start(job)


def _default_error(exc: Exception) -> None:
    if isinstance(exc, api_client.SessionExpiredError):
        return  # the expiry hook has already told the user and gone to sign-in
    if isinstance(exc, requests.RequestException):
        logger.warning("Background call could not reach the server: %s", exc)
    else:
        sys.excepthook(type(exc), exc, exc.__traceback__)


def _gone(widget) -> bool:
    try:
        return sip.isdeleted(widget)
    except TypeError:  # a plain Python object, not a Qt one
        return False


def load_async(owner, fetch, render) -> None:
    """Refresh a screen without freezing it: fetch() in the background, then render(value)."""
    generation = getattr(owner, "_load_generation", 0) + 1
    owner._load_generation = generation

    def current() -> bool:
        return not _gone(owner) and owner._load_generation == generation

    def ok(value):
        if current():
            render(value)

    def failed(exc):
        if not current():
            return
        if isinstance(exc, requests.RequestException):
            # server unreachable: keep the old rows and say so, like the synchronous path
            logger.warning("Could not refresh %s: backend unreachable", type(owner).__name__)
            window = owner.window() if hasattr(owner, "window") else None
            if window is not None and hasattr(window, "statusBar"):
                window.statusBar().showMessage(
                    "No connection to the server. This screen shows older data.", 8000
                )
        else:
            _default_error(exc)

    run_async(fetch, ok, failed)
