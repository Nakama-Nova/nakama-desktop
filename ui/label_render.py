"""
ui/label_render.py

Paints product stickers: the QR (with the Vriksha mark in the middle), the bar code, the
name, the price and the code. One painter serves the PDF, the printer and the preview, so
what you see is what prints. All measurements come in millimetres.
"""

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPdfWriter

from services import qr_service
from services.label_layouts import LabelFormat
from services.money import inr
from services.pricing import price_with_gst
from ui.assets import load_image, logo_path

BLACK, WHITE = QColor("#000000"), QColor("#FFFFFF")
MIN_BAR_MM = 0.19  # the narrowest bar a 200 dpi thermal head prints cleanly
CENTER = Qt.AlignmentFlag.AlignHCenter


def _font(px: float, bold=False) -> QFont:
    f = QFont()
    f.setPixelSize(max(1, round(px)))
    f.setBold(bold)
    return f


def paint_qr(p: QPainter, sku: str, box: QRectF, logo: QImage | None) -> None:
    """The QR for `sku` filling `box` (a square), with a white quiet zone and the logo on a plate."""
    matrix = qr_service.qr_matrix(sku)
    n = len(matrix)
    mod = max(1, int(min(box.width(), box.height()) // (n + 8)))  # whole device pixels: crisp edges
    side = mod * (n + 8)
    x0 = box.x() + (box.width() - side) / 2 + 4 * mod
    y0 = box.y() + (box.height() - side) / 2 + 4 * mod
    p.fillRect(QRectF(x0 - 4 * mod, y0 - 4 * mod, side, side), WHITE)
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                p.fillRect(QRectF(x0 + c * mod, y0 + r * mod, mod, mod), BLACK)
    if logo is None or logo.isNull():
        return
    size = qr_service.LOGO_FRACTION * n * mod
    plate = size + 2 * mod
    cx, cy = x0 + n * mod / 2, y0 + n * mod / 2
    p.fillRect(QRectF(cx - plate / 2, cy - plate / 2, plate, plate), WHITE)
    scale = size / max(logo.width(), logo.height())
    w, h = logo.width() * scale, logo.height() * scale
    p.drawImage(QRectF(cx - w / 2, cy - h / 2, w, h), logo)


def paint_barcode(p: QPainter, sku: str, box: QRectF, k: float) -> bool:
    """Code 128 across `box`. Returns False (and draws nothing) when it would be too narrow to scan."""
    bars = qr_service.barcode_bars(sku)
    if not bars:  # a code with letters Code 128 cannot hold: the QR alone carries it
        return False
    mod = box.width() / len(bars)
    if mod < MIN_BAR_MM * k:
        return False
    mod = min(mod, 0.45 * k)
    x0 = box.x() + (box.width() - mod * len(bars)) / 2
    i = 0
    while i < len(bars):
        if bars[i] == "1":
            j = i
            while j < len(bars) and bars[j] == "1":
                j += 1
            p.fillRect(QRectF(x0 + i * mod, box.y(), (j - i) * mod, box.height()), BLACK)
            i = j
        else:
            i += 1
    return True


def _text(p, rect: QRectF, text: str, px: float, bold=False, align=Qt.AlignmentFlag.AlignLeft, lines=1):
    p.setFont(_font(px, bold))
    p.setPen(BLACK)
    if lines == 1:
        text = QFontMetricsF(p.font()).elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        p.drawText(rect, int(align | Qt.AlignmentFlag.AlignVCenter), text)
    else:
        p.save()
        p.setClipRect(rect)
        p.drawText(rect, int(align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), text)
        p.restore()


def paint_label(p: QPainter, k: float, x: float, y: float, fmt: LabelFormat, item: dict, logo, brand=None) -> None:
    """One label with its top-left corner at (x, y) mm. k = device pixels per mm."""
    sku = item.get("sku") or ""
    name = item.get("name") or ""
    price = inr(price_with_gst(item)) if fmt.price else ""
    pad = (1.0 if fmt.w < 45 else 1.8) * k
    X, Y, W, H = x * k, y * k, fmt.w * k, fmt.h * k
    p.save()
    p.setClipRect(QRectF(X, Y, W, H))
    if fmt.h >= fmt.w:  # tall: hang tag, card
        top = Y + pad
        if brand is not None and not brand.isNull():  # the full Vriksha Studios logo on top
            bh = H * 0.13
            s = min((W - 2 * pad) / brand.width(), bh / brand.height())
            bw_, bh_ = brand.width() * s, brand.height() * s
            p.drawImage(QRectF(X + (W - bw_) / 2, top, bw_, bh_), brand)
            top += bh_ + pad
        _text(p, QRectF(X + pad, top, W - 2 * pad, 0.12 * H), name, 0.045 * H, True, CENTER, lines=2)
        top += 0.12 * H + pad / 2
        q = min(W - 2 * pad, 0.42 * H)
        paint_qr(p, sku, QRectF(X + (W - q) / 2, top, q, q), logo)
        top += q + pad / 2
        bar = QRectF(X + pad, top, W - 2 * pad, 0.09 * H)
        if paint_barcode(p, sku, bar, k):
            top += bar.height() + pad / 4
        _text(p, QRectF(X + pad, top, W - 2 * pad, 0.05 * H), sku, 0.038 * H, False, CENTER)
        top += 0.05 * H
        if price:
            _text(p, QRectF(X + pad, top, W - 2 * pad, 0.07 * H), price, 0.05 * H, True, CENTER)
    else:  # wide: QR on the left, words and bar code on the right
        q = min(H - 2 * pad, W * 0.45)
        paint_qr(p, sku, QRectF(X + pad, Y + (H - q) / 2, q, q), logo)
        rx = X + pad + q + pad
        rw = X + W - pad - rx
        row = H - 2 * pad
        _text(p, QRectF(rx, Y + pad, rw, row * 0.38), name, row * 0.17, True, lines=2)
        cur = Y + pad + row * 0.40
        if price:
            _text(p, QRectF(rx, cur, rw, row * 0.2), price, row * 0.17, True)
            cur += row * 0.21
        bar = QRectF(rx, cur, rw, row * 0.22)
        if paint_barcode(p, sku, bar, k):
            cur += bar.height() + row * 0.02
        _text(p, QRectF(rx, cur, rw, Y + H - pad - cur), sku, row * 0.13)
    p.restore()


def _setup_page(device, fmt: LabelFormat) -> None:
    w, h = fmt.page
    device.setPageSize(QPageSize(QSizeF(w, h), QPageSize.Unit.Millimeter))
    device.setPageMargins(QMarginsF(0, 0, 0, 0))


def render(device, fmt: LabelFormat, items: list[dict], start: int = 0) -> None:
    """Paint one label per entry of `items` (repeat an item for several copies) onto a
    QPdfWriter or QPrinter. `start` skips that many places on the first sheet."""
    _setup_page(device, fmt)
    k = device.logicalDpiX() / 25.4
    logo, brand = load_image(logo_path(short=True)), load_image(logo_path())
    p = QPainter(device)
    try:
        for i, item in enumerate(items):
            slot = (start + i) % fmt.per_page
            if i and slot == 0:
                device.newPage()
            x, y = fmt.origin(slot)
            paint_label(p, k, x, y, fmt, item, logo, brand)
    finally:
        p.end()


def save_pdf(path: str, fmt: LabelFormat, items: list[dict], start: int = 0) -> None:
    writer = QPdfWriter(path)
    writer.setResolution(600)
    writer.setTitle("Vriksha Studios labels")
    render(writer, fmt, items, start)


def label_image(fmt: LabelFormat, item: dict, dpi: int = 300) -> QImage:
    """One label as a picture: the preview, and what the tests scan."""
    k = dpi / 25.4
    img = QImage(round(fmt.w * k), round(fmt.h * k), QImage.Format.Format_RGB32)
    img.fill(WHITE)
    p = QPainter(img)
    paint_label(p, k, 0, 0, fmt, item, load_image(logo_path(short=True)), load_image(logo_path()))
    p.end()
    return img
