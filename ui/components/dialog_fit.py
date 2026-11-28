"""
ui/components/dialog_fit.py

Keeps every dialog on the screen it opens on.

Dialogs are laid out for the room they need (some want 900 px across or 640 down). On a
laptop screen, especially with Windows scaling at 125 or 150 per cent, that is more than the
screen has: the dialog opened with its bottom (and its Save button) off the screen, or half
outside it. Now, when a dialog is shown:

  * one that is bigger than the screen gets a scroll area around its contents and is capped to
    the screen, so everything in it can be reached;
  * one that opens partly off the screen is moved back onto it.

A dialog that fits is left exactly as it was. Message boxes, file and print dialogs are native
and size themselves, so they are not touched.
"""

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QFileDialog, QFrame, QMessageBox, QProgressDialog, QScrollArea, QVBoxLayout, QWidget

MARGIN = 48  # kept clear of the screen's edges (the title bar and the taskbar)
_SKIP = (QMessageBox, QFileDialog, QProgressDialog)


def available_area(dialog: QDialog):
    """The usable part of the screen the dialog's parent window is on (else the main screen)."""
    parent = dialog.parentWidget()
    screen = parent.screen() if parent is not None else None
    screen = screen or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def needs_scrolling(dialog: QDialog, area) -> bool:
    hint = dialog.minimumSizeHint().expandedTo(dialog.minimumSize())
    return hint.width() > area.width() - MARGIN or hint.height() > area.height() - MARGIN


def _wrap_in_scroll_area(dialog: QDialog) -> None:
    """Put the dialog's whole layout inside a scroll area."""
    layout = dialog.layout()
    if layout is None:
        return
    holder = QWidget()
    holder.setLayout(layout)  # takes the layout off the dialog
    holder.setObjectName("dialogContents")
    holder.setStyleSheet("QWidget#dialogContents { background: transparent; }")
    scroll = QScrollArea()
    scroll.setObjectName("dialogScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea#dialogScroll { background: transparent; border: none; }")
    scroll.setWidget(holder)
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll)
    dialog.setMinimumSize(0, 0)  # the contents scroll now; the dialog itself may shrink to the screen


def fit_dialog(dialog: QDialog) -> None:
    """Make sure the dialog fits the screen (see the module note). Safe to call more than once."""
    if isinstance(dialog, _SKIP) or dialog.property("screen_fitted"):
        return
    dialog.setProperty("screen_fitted", True)
    area = available_area(dialog)
    max_w, max_h = area.width() - MARGIN, area.height() - MARGIN
    if needs_scrolling(dialog, area):
        want = dialog.sizeHint()
        _wrap_in_scroll_area(dialog)
        # a little wider than the contents want: the vertical scroll bar takes some of the width
        dialog.resize(min(max(want.width() + 24, 420), max_w), min(max(want.height(), 320), max_h))
    dialog.setMaximumSize(max_w, max_h)
    QTimer.singleShot(0, lambda d=dialog: _move_onto_screen(d))


def _move_onto_screen(dialog: QDialog) -> None:
    try:
        if not dialog.isVisible():
            return
        area = available_area(dialog)
        frame = dialog.frameGeometry()
        x = min(max(frame.x(), area.left()), max(area.right() - frame.width() + 1, area.left()))
        y = min(max(frame.y(), area.top()), max(area.bottom() - frame.height() + 1, area.top()))
        if (x, y) != (frame.x(), frame.y()):
            dialog.move(x, y)
    except RuntimeError:  # the dialog was closed and deleted first
        pass


_installed = False


def install() -> None:
    """Fit every dialog this program shows. Once is enough."""
    global _installed
    if _installed:
        return
    _installed = True
    original = QDialog.showEvent

    def show_event(self, event):
        try:
            fit_dialog(self)
        except Exception:  # fitting is a courtesy: never let it stop a dialog from opening
            pass
        original(self, event)

    QDialog.showEvent = show_event
