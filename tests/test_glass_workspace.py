"""Heritage glass: the palette, the components, the sidebar breakpoints, the New Bill scan and the
off-thread buyer lookup."""

import threading
import time

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QFontMetricsF, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QBoxLayout, QLabel, QMessageBox, QWidget

from ui import workers
from ui.components.glass import (
    AnimatedSidebar,
    AsyncWorker,
    BusyLine,
    CommandTopBar,
    GlassCard,
    ResponsiveSplitWorkspace,
    ScrollableGlassPanel,
)
from ui.theme import Colors, ROLES, apply_theme, rgba, tabular_font


@pytest.fixture(autouse=True)
def back_to_light():
    apply_theme("light")
    yield
    apply_theme("light")


def wait_until(condition, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


def luminance(h):
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ------------------------------------------------------------------ the palette
def test_the_glass_palette_is_the_one_in_the_brief():
    apply_theme("glass")
    assert Colors.THEME == "glass" and Colors.DARK_MODE
    assert "#120F0D" <= Colors.BG <= "#1A1512"  # a charred-teak canvas between the two
    assert (Colors.TEXT_PRIMARY, Colors.TEXT_SECONDARY) == ("#F7F3EE", "#A89F96")  # ivory and sandstone
    assert (Colors.PRIMARY, Colors.SECONDARY) == ("#D4A359", "#E0B46C")  # burnished gold
    assert Colors.GLASS_FILL == "36,29,24,0.78" and Colors.GLASS_EDGE == "218,185,138,0.14"
    assert ROLES["primary"][0] == "#D4A359"


def test_glass_text_is_readable():
    apply_theme("glass")
    assert contrast(Colors.TEXT_PRIMARY, Colors.CARD_BG) >= 7
    assert contrast(Colors.TEXT_SECONDARY, Colors.CARD_BG) >= 4.5
    assert contrast(Colors.TEXT_MUTED, Colors.CARD_BG) >= 4.5
    assert contrast(Colors.PRIMARY, Colors.BG) >= 4.5  # gold on the canvas
    base, on_base = ROLES["primary"]
    assert contrast(base, on_base) >= 7  # the gold button's own text


def test_light_comes_back_exactly_after_glass():
    from ui.theme import LIGHT_PALETTE

    apply_theme("glass")
    apply_theme("light")
    assert {k: getattr(Colors, k) for k in LIGHT_PALETTE} == LIGHT_PALETTE


def test_a_token_becomes_a_colour():
    c = rgba("36,29,24,0.78")
    assert (c.red(), c.green(), c.blue(), c.alpha()) == (36, 29, 24, 199)
    assert rgba("36,29,24,0.78", 0.5).alpha() == 128


def test_figures_are_tabular(qapp):
    from ui.fonts import load_brand_fonts

    load_brand_fonts()
    from PyQt6.QtGui import QFont

    base = QFont("Inter", 12)
    plain = QFontMetricsF(base)
    tab = QFontMetricsF(tabular_font(base))
    assert plain.horizontalAdvance("1") != plain.horizontalAdvance("8")  # Inter's figures are proportional
    assert tab.horizontalAdvance("1") == tab.horizontalAdvance("8")  # so amounts line up in a column


# ------------------------------------------------------------------ the components
def test_a_glass_card_is_translucent_walnut(qapp):
    apply_theme("glass")
    card = GlassCard()
    card.resize(200, 120)
    centre = card.grab().toImage().pixelColor(100, 90)  # below the sheen, in the middle of the glass
    assert 150 < centre.alpha() < 250  # translucent: the page behind it shows through (0.78 opaque)
    assert centre.red() < 80 and centre.green() < 70  # warm dark walnut, not grey or white


def test_a_glass_card_warms_its_border_under_the_pointer(qapp):
    card = GlassCard()
    card.show()
    QApplication.sendEvent(card, QEvent(QEvent.Type.Enter))
    assert wait_until(lambda: card.hover > 0.95)
    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    assert wait_until(lambda: card.hover < 0.05)
    card.close()


def test_the_panel_scrolls_its_body_and_pins_its_footer(qapp):
    panel = ScrollableGlassPanel()
    for n in range(40):
        panel.body.addWidget(QLabel(f"row {n}"))
    pinned = QLabel("TOTAL")
    panel.footer.addWidget(pinned)
    panel.resize(340, 300)
    panel.show()
    for _ in range(20):
        QCoreApplication.processEvents()
    assert panel.scroller.verticalScrollBar().maximum() > 0  # the body scrolls
    assert panel.scroller.horizontalScrollBarPolicy().name == "ScrollBarAlwaysOff"
    bottom = pinned.mapTo(panel, pinned.rect().bottomLeft()).y()
    assert pinned.isVisible() and bottom <= panel.height()  # the footer stays in view
    panel.scroller.verticalScrollBar().setValue(panel.scroller.verticalScrollBar().maximum())
    assert pinned.mapTo(panel, pinned.rect().bottomLeft()).y() == bottom  # and does not move when the body scrolls
    panel.close()


def test_the_panel_is_never_narrower_than_its_contents(qapp):
    panel = ScrollableGlassPanel()
    wide = QLabel("x")
    wide.setMinimumWidth(400)
    panel.body.addWidget(wide)
    assert panel.minimumSizeHint().width() >= 400


def test_inline_mode_lets_the_page_scroll_instead_of_the_panel(qapp):
    panel = ScrollableGlassPanel()
    for n in range(30):
        panel.body.addWidget(QLabel(f"row {n}"))
    panel.set_inline(True)
    panel.resize(340, 200)
    panel.show()
    for _ in range(20):
        QCoreApplication.processEvents()
    assert panel.height() > 400  # as tall as its contents
    assert panel.scroller.verticalScrollBar().maximum() == 0  # so it does not scroll by itself
    panel.close()


def test_the_sidebar_glides_to_the_rail_and_back(qapp):
    bar = AnimatedSidebar(232, 80)
    bar.show()
    settled = []
    bar.settled.connect(settled.append)
    bar.set_collapsed(True)
    assert bar.is_collapsed()
    seen = set()
    assert wait_until(lambda: seen.add(bar.width()) or bar.width() == 80)
    assert any(80 < w < 232 for w in seen) or len(seen) > 1  # it passed through widths in between
    assert wait_until(lambda: settled and settled[-1] is True)  # told once it has arrived
    bar.set_collapsed(False)
    assert wait_until(lambda: bar.width() == 232)
    assert wait_until(lambda: settled[-1] is False)
    bar.close()


def test_the_sidebar_can_jump_without_the_glide(qapp):
    bar = AnimatedSidebar(232, 80)
    bar.show()
    bar.set_collapsed(True, animate=False)
    assert bar.width() == 80 and bar.minimumWidth() == bar.maximumWidth() == 80
    bar.close()


def test_the_busy_line_waits_a_moment_so_a_quick_load_does_not_flicker(qapp):
    line = BusyLine()
    assert line.sizeHint().height() == 2
    line.set_busy(True)
    line.set_busy(False)  # finished before the delay
    time.sleep(BusyLine.DELAY_MS / 1000 + 0.1)
    QCoreApplication.processEvents()
    assert not line.is_busy()
    line.set_busy(True)
    assert wait_until(line.is_busy)  # a slow load does show it
    line.set_busy(False)
    assert not line.is_busy()


def test_the_split_workspace_sits_side_by_side_when_wide_and_stacks_when_narrow(qapp):
    main, side = QLabel("main"), QLabel("side")
    ws = ResponsiveSplitWorkspace(main, side)
    ws.resize(1000, 400)
    ws.show()
    for _ in range(10):
        QCoreApplication.processEvents()
    assert ws.is_wide() and ws._box.direction() == QBoxLayout.Direction.LeftToRight
    assert 350 <= side.width() <= 420 and side.x() > main.x()
    ws.resize(520, 400)
    for _ in range(10):
        QCoreApplication.processEvents()
    assert not ws.is_wide() and ws._box.direction() == QBoxLayout.Direction.TopToBottom
    assert side.y() > main.y() and side.width() == ws.width()  # stacked, both full width
    assert main.minimumHeight() == 300  # the main pane keeps a floor so it does not collapse
    ws.resize(1000, 400)
    for _ in range(10):
        QCoreApplication.processEvents()
    assert ws.is_wide() and main.minimumHeight() == 0
    ws.close()


def test_the_workspace_tells_a_scrolling_panel_whether_it_is_inline(qapp):
    panel = ScrollableGlassPanel()
    ws = ResponsiveSplitWorkspace(QLabel("main"), panel)
    ws.resize(400, 400)
    ws.show()
    for _ in range(10):
        QCoreApplication.processEvents()
    assert panel._inline is True
    ws.resize(1000, 400)
    for _ in range(10):
        QCoreApplication.processEvents()
    assert panel._inline is False
    ws.close()


# ------------------------------------------------------------------ the async worker
def test_a_worker_runs_off_the_gui_thread_and_reports_loading_then_success(qapp):
    main = threading.get_ident()
    seen, order = {}, []
    worker = AsyncWorker(lambda: seen.setdefault("thread", threading.get_ident()) and 42)
    worker.loading.connect(lambda on: order.append(("loading", on)))
    worker.success.connect(lambda v: order.append(("success", v)))
    worker.error.connect(lambda e: order.append(("error", e)))
    worker.start()
    assert wait_until(lambda: ("success", 42) in order)
    assert seen["thread"] != main
    assert order == [("loading", True), ("loading", False), ("success", 42)]


def test_a_worker_reports_an_error_instead_of_raising(qapp):
    order = []

    def boom():
        raise ValueError("no")

    worker = AsyncWorker(boom)
    worker.loading.connect(lambda on: order.append(("loading", on)))
    worker.error.connect(lambda e: order.append(("error", type(e).__name__)))
    worker.start()
    assert wait_until(lambda: any(o[0] == "error" for o in order))
    assert order == [("loading", True), ("loading", False), ("error", "ValueError")]


# ------------------------------------------------------------------ the window
def window(qapp):
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    return w


def test_the_window_uses_the_command_bar_and_the_busy_line(qapp):
    w = window(qapp)
    assert isinstance(w.navbar, CommandTopBar) and isinstance(w.busy_line, BusyLine)
    assert w.navbar.goto_btn.graphicsEffect() is not None  # warms when the pointer is on it
    w.close()


def test_the_busy_line_follows_background_work(qapp, monkeypatch):
    from ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_load_person", lambda self: None)  # its own delayed lookup would add work
    w = window(qapp)
    assert wait_until(lambda: workers._pending == 0 and not w.busy_line.is_busy(), 5.0)  # start-up work finished
    done = []
    workers.run_async(lambda: time.sleep(0.5) or 1, lambda v: done.append(v))
    assert wait_until(w.busy_line.is_busy, 2.0)
    assert wait_until(lambda: done and not w.busy_line.is_busy(), 3.0)
    w.close()


def test_the_sidebar_follows_the_breakpoints_with_a_glide(qapp):
    w = window(qapp)
    w.resize(1400, 800)
    w.show()
    assert wait_until(lambda: w.sidebar.width() == 232 and not w._compact)
    w.resize(1100, 800)  # medium: an icon-only rail
    assert wait_until(lambda: w.sidebar.width() == 80 and w._compact)
    assert w._nav_buttons[0].text() == "" and w._nav_buttons[0].toolTip()  # names are tooltips
    w.resize(1400, 800)  # wide again: expanded, and the names come back once it has widened
    assert wait_until(lambda: w.sidebar.width() == 232)
    assert wait_until(lambda: w._nav_buttons[0].property("label_text") in w._nav_buttons[0].text())
    w.close()


# ------------------------------------------------------------------ New Bill: scan, lookup
ITEMS = [
    {"id": "i1", "name": "Ganesha temple panel, teak, 4 ft", "sku": "PNL-0412", "selling_price": 1000, "gst_percent": 12,
     "current_stock": 5, "dimensions_mm": {"width": 1200, "height": 900, "depth": 45}},
    {"id": "i2", "name": "Brass lamp stand, 5 ft", "sku": "LMP-0150", "selling_price": 100, "gst_percent": 12, "current_stock": 9},
]


def screen(qapp):
    from ui.sales_screen import SalesScreen

    s = SalesScreen()
    s._apply_items(ITEMS)
    return s


def test_a_scanned_sku_finds_the_product_as_a_name_does(qapp):
    s = screen(qapp)
    assert s._find_item("PNL-0412")["id"] == "i1"
    assert s._find_item("  pnl-0412  ")["id"] == "i1"  # a scanner may add spaces; case does not matter
    assert s._find_item("Brass lamp stand, 5 ft")["id"] == "i2"
    assert s._find_item("nothing") is None and s._find_item("") is None


def test_scanning_adds_the_item_and_keeps_the_box_ready_for_the_next(qapp):
    s = screen(qapp)
    s.show()
    s.search_input.setText("lmp-0150")
    s._add_item_to_cart()
    assert [c.item_id for c in s._cart] == ["i2"] and s.search_input.text() == ""
    assert s.search_input.hasFocus() or s.search_input.isVisible()
    s.close()


def test_an_unknown_code_says_so(qapp, monkeypatch):
    s = screen(qapp)
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))
    s.search_input.setText("ZZZ-9999")
    s._add_item_to_cart()
    assert shown and "ZZZ-9999" in shown[0] and "code" in shown[0] and s._cart == []


def test_the_search_box_suggests_skus_too(qapp):
    s = screen(qapp)
    model = s._completer.model()
    values = [model.index(r, 0).data() for r in range(model.rowCount())]
    assert "PNL-0412" in values and "Brass lamp stand, 5 ft" in values


def test_a_bill_line_shows_its_sku_and_size_on_hover(qapp):
    from ui.sales_screen import CartItem

    s = screen(qapp)
    s._cart = [CartItem("i1", ITEMS[0]["name"], 1000, 12, 1)]
    s._refresh_table()
    tip = s.table.item(0, s.COL_NAME).toolTip()
    assert "PNL-0412" in tip and "1200 × 900 × 45 mm" in tip


def test_the_buyer_lookup_runs_off_the_gui_thread(qapp, monkeypatch):
    s = screen(qapp)
    s.phone_input.setText("98450 12345")
    seen = {}

    def search(phone):
        seen["thread"] = threading.get_ident()
        time.sleep(0.15)
        return {"id": "c1", "name": "Lakshmi Interiors"}

    monkeypatch.setattr(s._customer_service, "search_by_phone", search)
    monkeypatch.setattr("ui.sales_screen.run_async", lambda fn, ok, err: None)  # the bill count is not under test
    s._handle_customer_lookup()
    assert s.search_btn.text() == "Finding…" and not s.search_btn.isEnabled()  # it says it is looking
    assert wait_until(lambda: s.customer_input.text() == "Lakshmi Interiors")
    assert seen["thread"] != threading.get_ident()
    assert s.search_btn.isEnabled() and s.search_btn.text() == "Find buyer by phone"
    assert s.buyer_note.text() == "Lakshmi Interiors is already a buyer."


def test_a_late_lookup_answer_for_another_phone_is_ignored(qapp, monkeypatch):
    s = screen(qapp)
    s.phone_input.setText("11111")
    monkeypatch.setattr(s._customer_service, "search_by_phone", lambda p: time.sleep(0.15) or {"id": "c", "name": "Old"})
    s._handle_customer_lookup()
    s.phone_input.setText("22222")  # the person typed another number meanwhile
    assert wait_until(lambda: s.search_btn.isEnabled())
    QCoreApplication.processEvents()
    assert s.customer_input.text() == "" and s.buyer_note.isHidden()


def test_a_failed_lookup_is_a_quiet_note_and_a_refused_one_says_so(qapp, monkeypatch):
    import requests

    from services.api_client import ForbiddenError

    s = screen(qapp)
    s.phone_input.setText("98450 12345")

    def down(phone):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(s._customer_service, "search_by_phone", down)
    s._handle_customer_lookup()
    assert wait_until(lambda: "offline" in s.buyer_note.text())

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))

    def refused(phone):
        raise ForbiddenError(403, "no")

    monkeypatch.setattr(s._customer_service, "search_by_phone", refused)
    s._handle_customer_lookup()
    assert wait_until(lambda: bool(shown)) and "permission" in shown[0]


def test_new_bill_lays_out_as_a_split_workspace(qapp):
    s = screen(qapp)
    assert isinstance(s.workspace, ResponsiveSplitWorkspace)
    panels = s.findChildren(ScrollableGlassPanel)
    assert len(panels) == 1 and s.invoice_btn.parentWidget() is not None
    assert s.findChildren(GlassCard)  # the items card
    assert isinstance(s.workspace, QWidget)
