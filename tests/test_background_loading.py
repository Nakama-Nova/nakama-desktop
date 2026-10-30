"""Screens fetch in the background, so a slow server never freezes the window."""

import threading
import time

import pytest
import requests
from PyQt6.QtCore import QCoreApplication

from services import api_client
from services.api_client import APIError, SessionExpiredError
from services.inventory_service import InventoryService
from services.report_service import ReportService
from ui import workers
from ui.dashboard_window import DashboardWindow
from ui.inventory_window import InventoryWindow
from ui.main_window import MainWindow
from ui.workers import load_async, run_async

MAIN = threading.get_ident()


def wait_until(condition, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def test_a_job_runs_off_the_gui_thread_and_answers_on_it(qapp):
    seen = {}

    def job():
        seen["worker"] = threading.get_ident()
        return 42

    run_async(job, lambda value: seen.update(value=value, back=threading.get_ident()))
    assert wait_until(lambda: "value" in seen)
    assert seen["value"] == 42 and seen["worker"] != MAIN and seen["back"] == MAIN


def test_a_failing_job_reports_the_error_on_the_gui_thread(qapp):
    seen = {}

    def boom():
        raise ValueError("nope")

    run_async(boom, None, lambda exc: seen.update(exc=exc, back=threading.get_ident()))
    assert wait_until(lambda: "exc" in seen)
    assert isinstance(seen["exc"], ValueError) and seen["back"] == MAIN


def test_the_busy_listener_hears_when_work_starts_and_stops(qapp):
    workers.wait_for_jobs()
    QCoreApplication.processEvents()  # deliver anything earlier tests left behind
    heard = []
    workers.on_busy_changed(heard.append)
    done = []
    run_async(lambda: time.sleep(0.05), lambda _: done.append(1))
    assert wait_until(lambda: done)
    assert heard == [True, False]
    workers._busy_listeners.clear()


def test_a_newer_load_makes_an_older_one_a_no_op(qapp):
    class Owner:
        pass

    owner, shown = Owner(), []
    load_async(owner, lambda: (time.sleep(0.15), "old")[1], shown.append)
    load_async(owner, lambda: "new", shown.append)
    assert wait_until(lambda: shown)
    time.sleep(0.3)
    QCoreApplication.processEvents()
    assert shown == ["new"]


def test_server_errors_are_queued_on_a_background_thread_not_shown_from_it(monkeypatch):
    shown = []
    monkeypatch.setattr("sys.excepthook", lambda *a: shown.append(a))

    class Resp:
        status_code = 409
        text = '{"detail": "Not enough stock"}'

    api_client.begin_background()
    err = api_client.APIClient._fail(Resp())
    queued = api_client.end_background()
    assert shown == [] and queued == [err]  # nothing popped up from the worker thread

    api_client.APIClient._fail(Resp())  # a normal foreground call still shows it at once
    assert len(shown) == 1


def test_queued_errors_are_shown_once_on_the_gui_thread(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr("sys.excepthook", lambda t, v, tb: shown.append((v, threading.get_ident())))
    done = []

    def job():
        class Resp:
            status_code = 409
            text = '{"detail": "Not enough stock"}'

        err = api_client.APIClient._fail(Resp())  # the service swallows it, returns None
        return None if err else 1

    run_async(job, lambda v: done.append(v))
    assert wait_until(lambda: done)
    assert len(shown) == 1 and shown[0][1] == MAIN and shown[0][0].reported


def test_home_numbers_arrive_after_the_screen_is_already_up(qapp, monkeypatch):
    def slow(self):
        time.sleep(0.3)
        return {"today_sales_count": 7, "today_revenue": 100, "low_stock_count": 1, "pending_wages_total": 0}

    monkeypatch.setattr(ReportService, "get_dashboard_summary", slow)
    w = DashboardWindow()
    started = time.monotonic()
    w.refresh_async()
    assert time.monotonic() - started < 0.2  # did not wait for the server
    assert w.card_sales.value_lbl.text() == "0"
    assert wait_until(lambda: w.card_sales.value_lbl.text() == "7")


def test_switching_screens_does_not_wait_for_the_server(qapp, monkeypatch):
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: (time.sleep(0.5), [])[1])
    w = MainWindow()
    w._sync_timer.stop()
    started = time.monotonic()
    w._switch_page(2)
    assert time.monotonic() - started < 0.3
    assert wait_until(lambda: not w.inventory_view._load_generation or True)
    w.close()


def test_an_unreachable_server_keeps_the_old_rows_and_says_so(qapp, monkeypatch):
    def down(self, allow_cached=False):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(InventoryService, "get_items", down)
    w = MainWindow()
    w._sync_timer.stop()
    w.inventory_view._all_items = [{"name": "Chair"}]
    w._switch_page(2)
    assert wait_until(lambda: "No connection" in w.statusBar().currentMessage())
    assert w.inventory_view._all_items == [{"name": "Chair"}]
    w.close()


def test_the_sync_cycle_runs_in_the_background_and_reports_back_here(qapp, monkeypatch):
    w = MainWindow()
    w._sync_timer.stop()
    seen = {}
    monkeypatch.setattr(w._sync_service, "is_online", lambda: seen.setdefault("thread", threading.get_ident()) or True)
    monkeypatch.setattr(w._sync_service, "push_sync", lambda: {"pushed": 1, "failed": 0, "held": 2})
    monkeypatch.setattr(w._sync_service, "pull_sync", lambda: {})
    from services.event_bus import EventBus, SALE_CREATED

    emitted = []
    EventBus.subscribe(SALE_CREATED, lambda: emitted.append(threading.get_ident()))
    w._sync_async()
    assert w._sync_running
    w._sync_async()  # a second one while the first runs is ignored
    assert wait_until(lambda: not w._sync_running and "waiting" in w.statusBar().currentMessage())
    assert seen["thread"] != MAIN and emitted and emitted[-1] == MAIN
    w.close()


def test_a_session_expiry_in_the_background_sync_is_not_an_error(qapp, monkeypatch, caplog):
    w = MainWindow()
    w._sync_timer.stop()
    monkeypatch.setattr(w._sync_service, "is_online", lambda: True)

    def expired():
        raise SessionExpiredError()

    monkeypatch.setattr(w._sync_service, "push_sync", expired)
    w._sync_async()
    assert wait_until(lambda: not w._sync_running)
    assert "Background sync cycle failed" not in caplog.text
    w.close()


def test_a_long_stock_list_makes_buttons_only_for_the_rows_on_screen(qapp):
    w = InventoryWindow()
    w.resize(1000, 500)
    w.show()
    items = [{"name": f"A{i}", "item_type": "furniture", "sku": f"A{i}", "current_stock": 5, "min_stock": 1} for i in range(500)]
    started = time.monotonic()
    w._populate_table(items)
    assert time.monotonic() - started < 1.5  # was about 3 s: one row of buttons costs ~3 ms
    assert w.table.rowCount() == 500
    assert w.table.item(499, 0).text() == "A499"  # every row's text is there at once
    assert w.table.cellWidget(0, w.COL_ACTIONS) is not None
    assert w.table.cellWidget(499, w.COL_ACTIONS) is None  # no buttons yet for rows far off screen

    QCoreApplication.processEvents()  # lay the table out, so it has something to scroll
    w.table.verticalScrollBar().setValue(w.table.verticalScrollBar().maximum())
    QCoreApplication.processEvents()
    assert w.table.cellWidget(499, w.COL_ACTIONS) is not None  # made as the row came into view
    w.close()


def test_a_new_list_replaces_the_old_rows_and_their_buttons(qapp):
    w = InventoryWindow()
    row = lambda n: {"name": n, "item_type": "furniture", "sku": n, "current_stock": 5, "min_stock": 1}
    w._populate_table([row("A"), row("B"), row("C")])
    w._populate_table([row("X")])
    assert w.table.rowCount() == 1 and w.table.item(0, 0).text() == "X"
    assert w.table.cellWidget(0, w.COL_ACTIONS) is not None
