"""With the server down the app must still open (the counter bills offline)."""

from ui.attendance_screen import AttendanceScreen
from conftest import settle
from ui.main_window import MainWindow



def test_main_window_opens_without_a_server(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    assert w.content_stack.count() == 21


def test_opening_a_screen_offline_shows_a_notice_not_a_crash(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._switch_page(2)  # Stock: refresh hits the dead server
    settle()
    assert "No connection" in w.statusBar().currentMessage()


def test_workforce_screen_builds_without_a_server(qapp):
    AttendanceScreen()


def test_keyboard_shortcuts_move_around_and_find_the_search_box(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w.show()
    assert len(w._shortcuts) == 11  # F5, Ctrl+F, Ctrl+1..9
    second = next(i for i, b in w._nav_mapping.items() if b is w._nav_buttons[1])
    w._go_to_nth(2)
    assert w.content_stack.currentIndex() == second
    w._switch_page(18, refresh=False)  # Places has a search box
    w._focus_search()
    assert w.focusWidget() is w.places_view.search
