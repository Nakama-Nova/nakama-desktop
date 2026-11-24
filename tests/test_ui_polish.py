"""Line icons, brand tabs, arrow assets and money formatting across screens."""

import re

from PyQt6.QtWidgets import QTabWidget

from ui import icons
from ui.assets import ICON_DIR
from ui.main_window import MainWindow
from ui.theme import Theme


def test_every_sidebar_entry_has_its_own_line_icon(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    labels = [label for _, label, _ in w.NAV_ITEMS]
    assert all(label in icons.FOR_LABEL for label in labels)
    assert all(icons.FOR_LABEL[label] in icons._PATHS for label in labels)
    for btn in w._nav_buttons:
        assert not btn.icon().isNull()
        assert "🏠" not in btn.text()  # no emoji left in the sidebar
    w.close()


def test_an_icon_is_drawn_in_the_colour_asked(qapp):
    image = icons.pixmap("home", "#5A2A06", 18, 1.0).toImage()
    solid = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 200]
    assert solid
    for c in solid:  # within 2 per channel: the renderer's alpha rounding can shift one
        assert abs(c.red() - 0x5A) <= 2 and abs(c.green() - 0x2A) <= 2 and abs(c.blue() - 0x06) <= 2


def test_the_arrows_the_input_style_points_at_exist(qapp):
    urls = re.findall(r"url\(([^)]+)\)", Theme.input_style())
    assert len(urls) >= 3
    for u in urls:
        assert u.endswith(".png") and (ICON_DIR / u.rsplit("/", 1)[-1]).exists()


def test_tabs_become_brand_pills(qapp):
    t = QTabWidget()
    Theme.style_tabs(t)
    assert t.documentMode() and "QTabBar::tab:selected" in t.styleSheet()


def test_other_screens_also_read_in_lakhs():
    from ui.machines_screen import money

    assert money(246500) == "₹2,46,500.00"
    assert money(-100000) == "-₹1,00,000.00"
