"""
ui/receipt_render.py

A bill as a receipt on paper: an 80 mm or 58 mm thermal roll, A5 or A4. Drawn on the PC from
the bill's own figures, so it prints with no connection too. The official tax invoice is the
server's PDF; a receipt made while offline says "Provisional" until the bill is synced.
"""

from datetime import datetime

from PyQt6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPdfWriter

from services.money import inr
from ui.assets import load_image, logo_path
from ui.label_render import paint_barcode

BLACK, WHITE = QColor("#000000"), QColor("#FFFFFF")
LEFT, RIGHT, CENTER = Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignHCenter
WRAP = Qt.TextFlag.TextWordWrap

# key, title, width mm, page height mm (None: a roll, as long as the bill), text size mm, margin mm
FORMATS = [
    ("thermal_80", "80 mm thermal roll", 80, None, 3.0, 4),
    ("thermal_58", "58 mm thermal roll", 58, None, 2.7, 3),
    ("a5", "A5 paper", 148, 210, 3.8, 10),
    ("a4", "A4 paper", 210, 297, 4.1, 14),
]
BY_KEY = {f[0]: f for f in FORMATS}


def _num(v) -> float:
    return float(v or 0)


def receipt_from_sale(sale: dict, items: list[dict], shop: dict | None = None, provisional: bool = False) -> dict:
    """What the receipt prints, from a bill (the server's, or one made from the cart while offline)."""
    lines = []
    for it in items or []:
        qty, price = _num(it.get("quantity")), _num(it.get("price_at_sale"))
        gst_pct = _num(it.get("gst_percent"))
        lines.append({
            "name": it.get("item_name") or "Item", "qty": qty, "price": price, "gst_pct": gst_pct,
            "amount": _num(it.get("total_price")) or price * qty * (1 + gst_pct / 100),
        })
    sub = _num(sale.get("sub_total")) or sum(ln["price"] * ln["qty"] for ln in lines)
    cgst = sum(_num(it.get("cgst_amount")) for it in items or [])
    sgst = sum(_num(it.get("sgst_amount")) for it in items or [])
    tax = _num(sale.get("tax_total")) or cgst + sgst or sum(ln["price"] * ln["qty"] * ln["gst_pct"] / 100 for ln in lines)
    if not (cgst or sgst):
        cgst = sgst = tax / 2
    discount = _num(sale.get("discount"))
    total = _num(sale.get("total_amount")) or sub + tax - discount
    paid = sale.get("amount_paid")
    if paid is None and sale.get("payment_status") == "paid":
        paid = total
    return {
        "shop": shop or {}, "provisional": provisional, "number": sale.get("invoice_number") or "",
        "date": str(sale.get("invoice_date") or sale.get("created_at") or datetime.now().isoformat())[:10],
        "buyer": {"name": sale.get("customer_name"), "phone": sale.get("customer_phone"), "gstin": sale.get("customer_gstin")},
        "lines": lines, "sub": sub, "cgst": cgst, "sgst": sgst, "discount": discount, "total": total,
        "paid": None if paid is None else _num(paid),
        "balance": _num(sale["balance_due"]) if sale.get("balance_due") is not None else (None if paid is None else max(0.0, total - _num(paid))),
        "method": sale.get("payment_method"),
    }


class _Pen:
    """Paints one receipt top to bottom; with draw=False it only measures."""

    def __init__(self, p: QPainter, k: float, w_mm: float, size_mm: float, margin_mm: float, draw: bool):
        self.p, self.k, self.draw = p, k, draw
        self.x, self.w = margin_mm * k, (w_mm - 2 * margin_mm) * k
        self.px = size_mm * k
        self.y = margin_mm * k

    def _font(self, scale=1.0, bold=False) -> QFont:
        f = QFont()
        f.setPixelSize(max(1, round(self.px * scale)))
        f.setBold(bold)
        return f

    def text(self, s: str, align=LEFT, scale=1.0, bold=False, x=None, w=None, advance=True) -> float:
        f = self._font(scale, bold)
        x, w = self.x if x is None else x, self.w if w is None else w
        h = QFontMetricsF(f).boundingRect(QRectF(0, 0, w, 0), int(align | WRAP), s).height()
        if self.draw:
            self.p.setFont(f)
            self.p.setPen(BLACK)
            self.p.drawText(QRectF(x, self.y, w, h), int(align | WRAP), s)
        if advance:
            self.y += h
        return h

    def pair(self, left: str, right: str, scale=1.0, bold=False):
        h = max(self.text(left, LEFT, scale, bold, w=self.w * 0.62, advance=False), self.text(right, RIGHT, scale, bold, x=self.x + self.w * 0.62, w=self.w * 0.38, advance=False))
        self.y += h

    def gap(self, mm=1.5):
        self.y += mm * self.k

    def rule(self):
        self.y += 0.4 * self.k
        if self.draw:
            self.p.fillRect(QRectF(self.x, self.y, self.w, max(1, 0.2 * self.k)), BLACK)
        self.y += 0.8 * self.k

    def image(self, img: QImage, max_h_mm: float):
        if img.isNull():
            return
        s = min(self.w * 0.7 / img.width(), max_h_mm * self.k / img.height())
        w, h = img.width() * s, img.height() * s
        if self.draw:
            self.p.drawImage(QRectF(self.x + (self.w - w) / 2, self.y, w, h), img)
        self.y += h + self.k

    def barcode(self, number: str, h_mm=9):
        if self.draw:
            paint_barcode(self.p, number, QRectF(self.x, self.y, self.w, h_mm * self.k), self.k)
        self.y += (h_mm + 1) * self.k


def payslip_from_payment(payment: dict, name: str, role: str | None = None, shop: dict | None = None) -> dict:
    """What a pay slip prints, from one pay-out (the server's payment row)."""
    daily, extras = _num(payment.get("gross_daily")), _num(payment.get("gross_extras"))
    return {
        "payslip": True, "shop": shop or {}, "name": name, "role": role or "", "date": str(payment.get("paid_on") or "")[:10],
        "method": str(payment.get("method") or ""), "daily": daily, "extras": extras, "gross": daily + extras,
        "deductions": _num(payment.get("deductions")), "net": _num(payment.get("net_paid")), "number": "",
    }


def _paint_payslip(p, k, fmt, r: dict, draw: bool) -> float:
    _key, _title, w_mm, _h, size, margin = fmt
    pen = _Pen(p, k, w_mm, size, margin, draw)
    shop = r["shop"]
    pen.image(load_image(logo_path()), 14 if w_mm >= 140 else 12)
    pen.text(shop.get("name") or "Vriksha Studios", CENTER, 1.3, True)
    if shop.get("address"):
        pen.text(str(shop["address"]), CENTER, 0.85)
    pen.gap()
    pen.rule()
    pen.text("PAY SLIP", CENTER, 1.2, True)
    pen.gap(1)
    pen.pair("Name", r["name"], 1.0, True)
    if r["role"]:
        pen.pair("Role", r["role"], 0.95)
    pen.pair("Paid on", r["date"], 0.95)
    pen.pair("Paid by", r["method"].upper() if r["method"] == "upi" else r["method"].title(), 0.95)
    pen.rule()
    pen.pair("Daily wages", inr(r["daily"]), 1.0)
    pen.pair("Piece work, overtime, bonus", inr(r["extras"]), 1.0)
    pen.pair("Total earned", inr(r["gross"]), 1.0, True)
    if r["deductions"]:
        pen.pair("Taken back from advance", f"-{inr(r['deductions'])}", 1.0)
    pen.rule()
    pen.pair("NET PAID", inr(r["net"]), 1.3, True)
    pen.gap(8)
    pen.pair("Received by: ____________", "Paid by: ____________", 0.9)
    pen.gap(2)
    pen.text("Thank you for your work.", CENTER, 0.9)
    return (pen.y / k) + margin


def _paint(p, k, fmt, r: dict, draw: bool) -> float:
    """Draw the receipt (or pay slip); returns how far down it goes, in mm."""
    if r.get("payslip"):
        return _paint_payslip(p, k, fmt, r, draw)
    _key, _title, w_mm, _h, size, margin = fmt
    pen = _Pen(p, k, w_mm, size, margin, draw)
    wide = w_mm >= 140
    shop = r["shop"]
    pen.image(load_image(logo_path()), 14 if wide else 12)
    pen.text(shop.get("name") or "Vriksha Studios", CENTER, 1.3, True)
    for key in ("tagline", "address", "phone"):
        if shop.get(key):
            pen.text(("Ph: " if key == "phone" else "") + str(shop[key]), CENTER, 0.85)
    if shop.get("gstin"):
        pen.text(f"GSTIN: {shop['gstin']}", CENTER, 0.9)
    pen.gap()
    pen.rule()
    pen.text("PROVISIONAL RECEIPT" if r["provisional"] else ("TAX INVOICE" if shop.get("gstin") else "BILL"), CENTER, 1.1, True)
    if r["provisional"]:
        pen.text("Not a tax invoice. The official bill number is given once this bill reaches the server.", CENTER, 0.8)
    pen.pair(f"No: {r['number']}", r["date"], 0.95)
    b = r["buyer"]
    who = " · ".join(x for x in (b.get("name"), b.get("phone")) if x)
    if who:
        pen.text(f"Buyer: {who}", LEFT, 0.95)
    if b.get("gstin"):
        pen.text(f"Buyer GSTIN: {b['gstin']}", LEFT, 0.95)
    pen.rule()
    for ln in r["lines"]:
        qty = f"{ln['qty']:g}"
        if wide:
            pen.text(ln["name"], LEFT, 1.0, True)
            pen.pair(f"{qty} × {inr(ln['price'])}" + (f"   GST {ln['gst_pct']:g}%" if ln["gst_pct"] else ""), inr(ln["amount"]), 0.95)
        else:
            pen.text(ln["name"], LEFT, 1.0, True)
            pen.pair(f"{qty} × {inr(ln['price'])}" + (f" +{ln['gst_pct']:g}%" if ln["gst_pct"] else ""), inr(ln["amount"]), 0.95)
        pen.gap(0.6)
    pen.rule()
    pen.pair("Subtotal (before GST)", inr(r["sub"]), 0.95)
    if r["cgst"] or r["sgst"]:
        pen.pair("CGST", inr(r["cgst"]), 0.95)
        pen.pair("SGST", inr(r["sgst"]), 0.95)
    if r["discount"]:
        pen.pair("Discount", f"-{inr(r['discount'])}", 0.95)
    pen.pair("TOTAL", inr(r["total"]), 1.25, True)
    if r["paid"] is not None:
        pen.pair("Paid" + (f" ({r['method']})" if r["method"] else ""), inr(r["paid"]), 0.95)
        if r["balance"]:
            pen.pair("Balance to pay", inr(r["balance"]), 1.0, True)
    pen.gap()
    if r["number"] and not r["provisional"]:
        pen.barcode(r["number"])
    pen.text("Thank you. Handcrafted with care.", CENTER, 0.9)
    return (pen.y / k) + margin


def render(device, fmt, receipt: dict) -> None:
    """Paint onto a QPdfWriter or QPrinter. A roll's page is as long as the bill needs."""
    key, _t, w_mm, h_mm, _s, _m = fmt
    k = device.logicalDpiX() / 25.4
    probe = QImage(10, 10, QImage.Format.Format_RGB32)
    pp = QPainter(probe)
    height = h_mm or max(40.0, _paint(pp, k, fmt, receipt, False))
    pp.end()
    device.setPageSize(QPageSize(QSizeF(w_mm, height), QPageSize.Unit.Millimeter))
    device.setPageMargins(QMarginsF(0, 0, 0, 0))
    p = QPainter(device)
    try:
        _paint(p, k, fmt, receipt, True)
    finally:
        p.end()


def save_pdf(path: str, fmt, receipt: dict) -> None:
    w = QPdfWriter(path)
    w.setResolution(300)
    w.setTitle("Vriksha Studios receipt")
    render(w, fmt, receipt)


def receipt_image(fmt, receipt: dict, dpi: int = 120) -> QImage:
    """The receipt as a picture, for the preview."""
    k = dpi / 25.4
    probe = QImage(10, 10, QImage.Format.Format_RGB32)
    pp = QPainter(probe)
    height = fmt[3] or max(40.0, _paint(pp, k, fmt, receipt, False))
    pp.end()
    img = QImage(round(fmt[2] * k), round(height * k), QImage.Format.Format_RGB32)
    img.fill(WHITE)
    p = QPainter(img)
    _paint(p, k, fmt, receipt, True)
    p.end()
    return img
