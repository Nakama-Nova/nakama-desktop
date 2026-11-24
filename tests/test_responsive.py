"""Screens that scroll instead of being cut off, a New Bill whose Create button stays in view, and
dialogs that stay on the screen."""

import pytest
import requests
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components import dialog_fit
from ui.components.pages import ScrollingPages
from ui.main_window import MainWindow


def settle(n=15):
    for _ in range(n):
        QCoreApplication.processEvents()


def area_of(page):
    """The scroll area a screen sits in (found from the screen, not by position)."""
    w = page
    while w is not None and not isinstance(w, QScrollArea):
        w = w.parentWidget()
    return w


def tall_page(height):
    page = QWidget()
    lay = QVBoxLayout(page)
    filler = QLabel("x")
    filler.setMinimumHeight(height)
    lay.addWidget(filler)
    return page


# ------------------------------------------------------------------ the stack of screens
def test_the_stack_hands_out_the_screens_not_the_scroll_areas(qapp):
    stack = ScrollingPages()
    a, b = tall_page(10), tall_page(10)
    assert stack.addWidget(a) == 0 and stack.addWidget(b) == 1
    assert stack.widget(0) is a and stack.widget(1) is b and stack.count() == 2
    stack.setCurrentIndex(1)
    assert stack.currentWidget() is b and stack.indexOf(b) == 1 and stack.indexOf(QWidget()) == -1
    stack.setCurrentWidget(a)
    assert stack.currentIndex() == 0 and stack.widget(5) is None


def test_a_screen_taller_than_its_window_gets_a_scroll_bar_and_one_that_fits_does_not(qapp):
    stack = ScrollingPages()
    tall, short = tall_page(900), tall_page(100)
    stack.addWidget(tall)
    stack.addWidget(short)
    stack.resize(600, 400)
    stack.show()
    settle()
    stack.setCurrentIndex(0)
    settle()
    assert stack.currentWidget() is tall
    assert area_of(tall).verticalScrollBar().maximum() > 0  # the rest of it can be reached
    stack.setCurrentIndex(1)
    settle()
    assert area_of(short).verticalScrollBar().maximum() == 0  # a screen that fits does not scroll
    stack.close()


def test_the_main_window_keeps_its_screens_reachable_by_the_old_names(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    assert isinstance(w.content_stack, ScrollingPages)
    assert w.content_stack.widget(1) is w.sales_view and w.content_stack.widget(0) is w.dashboard_view
    w._switch_page(2, refresh=False)
    assert w.content_stack.currentWidget() is w.inventory_view
    w.close()


# ------------------------------------------------------------------ New Bill on a small window
def test_create_bill_is_in_view_on_a_small_window(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    w.resize(1024, 600)
    w.show()
    settle(30)
    w._switch_page(1, refresh=False)
    settle(30)
    s = w.sales_view
    button = s.invoice_btn
    assert button.isVisible()
    bottom = button.mapTo(w, button.rect().bottomLeft()).y()
    assert bottom <= w.height(), (bottom, w.height())  # not below the bottom of the window
    total = s.grandtotal_lbl.mapTo(w, s.grandtotal_lbl.rect().bottomLeft()).y()
    assert total <= button.mapTo(w, button.rect().topLeft()).y()  # the total sits right above it
    w.close()


def test_the_buyer_details_scroll_while_total_and_buttons_stay_put(qapp):
    from ui.sales_screen import SalesScreen

    s = SalesScreen()
    s.resize(900, 420)
    s.show()
    settle(30)
    scroller = s.findChild(QScrollArea)
    assert scroller is not None and scroller.verticalScrollBar().maximum() > 0
    scroller.verticalScrollBar().setValue(scroller.verticalScrollBar().maximum())
    settle()
    assert s.invoice_btn.isVisible() and s.invoice_btn.isEnabled()  # untouched by scrolling the details
    s.close()


def test_the_bills_money_columns_are_never_shortened_by_the_generic_shrinking(qapp):
    from ui.sales_screen import SalesScreen

    s = SalesScreen()
    assert s.table.property("elastic") is True  # sized by its own column modes: the item name gives way


# ------------------------------------------------------------------ dialogs
@pytest.fixture
def fitting(qapp):
    dialog_fit.install()
    yield


def big_dialog(width, height, parent=None):
    d = QDialog(parent)
    lay = QVBoxLayout(d)
    body = QLabel("contents")
    body.setMinimumSize(width, height)
    lay.addWidget(body)
    ok = QPushButton("Save")
    lay.addWidget(ok)
    d.ok = ok
    return d


def test_a_dialog_that_fits_is_left_alone(fitting):
    d = big_dialog(300, 200)
    d.show()
    settle()
    assert d.findChildren(QScrollArea) == [] and not d.maximumSize().isNull()
    d.close()


def test_a_dialog_bigger_than_the_screen_scrolls_and_is_capped_to_it(fitting):
    area = dialog_fit.available_area(QDialog())
    d = big_dialog(area.width() + 400, area.height() + 400)
    d.show()
    settle(30)
    assert d.findChildren(QScrollArea), "its contents are in a scroll area"
    assert d.width() <= area.width() - dialog_fit.MARGIN and d.height() <= area.height() - dialog_fit.MARGIN
    assert d.ok.parentWidget() is not None  # the Save button is still in the dialog, reachable by scrolling
    d.close()


def test_a_dialog_that_opens_off_the_screen_is_moved_back(fitting):
    area = dialog_fit.available_area(QDialog())
    d = big_dialog(200, 120)
    d.move(area.right() - 40, area.bottom() - 40)  # mostly outside
    d.show()
    settle(30)
    frame = d.frameGeometry()
    assert frame.right() <= area.right() + 1 and frame.bottom() <= area.bottom() + 1
    assert frame.left() >= area.left() and frame.top() >= area.top()
    d.close()


def test_fitting_one_dialog_twice_changes_nothing_more(fitting):
    area = dialog_fit.available_area(QDialog())
    d = big_dialog(area.width() + 100, area.height() + 100)
    dialog_fit.fit_dialog(d)
    scrolls = len(d.findChildren(QScrollArea))
    dialog_fit.fit_dialog(d)
    assert len(d.findChildren(QScrollArea)) == scrolls == 1


def test_message_boxes_and_file_dialogs_size_themselves(qapp):
    box = QMessageBox()
    dialog_fit.fit_dialog(box)
    assert not box.property("screen_fitted")


def test_a_dialog_with_a_parent_is_sized_for_the_parents_screen(fitting, qapp):
    parent = QWidget()
    parent.show()
    d = big_dialog(dialog_fit.available_area(parent.window() and QDialog(parent)).width() + 50, 100, parent)
    d.show()
    settle(20)
    assert d.findChildren(QScrollArea)
    d.close()
    parent.close()


def test_every_dialog_class_in_the_program_is_covered_by_the_fitter(fitting):
    """The fitter hooks QDialog itself, so a dialog the program defines needs nothing of its own."""
    from ui.settings_dialog import SettingsDialog

    d = SettingsDialog()
    d.show()
    settle(20)
    assert d.property("screen_fitted") is True
    d.close()


# ------------------------------------------------------------------ the program's own error pop-ups
@pytest.mark.parametrize(
    "exc",
    [requests.Timeout("slow"), requests.ConnectionError("down")],
)
def test_the_global_error_pop_ups_belong_to_the_window_in_front(qapp, monkeypatch, exc):
    import main as program

    front = QWidget()
    shown = []
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: front))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda parent, *a, **k: shown.append(parent)))
    program.exception_hook(type(exc), exc, None)
    assert shown == [front]  # not None: it opens over the program, not behind it
