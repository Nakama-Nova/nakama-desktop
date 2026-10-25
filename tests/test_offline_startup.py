"""With the server down the app must still open (the counter bills offline)."""

from ui.attendance_screen import AttendanceScreen
from ui.main_window import MainWindow


def test_main_window_opens_without_a_server(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    assert w.content_stack.count() == 7


def test_opening_a_screen_offline_shows_a_notice_not_a_crash(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._switch_page(2)  # Stock: refresh hits the dead server
    assert "No connection" in w.statusBar().currentMessage()


def test_workforce_screen_builds_without_a_server(qapp):
    AttendanceScreen()
