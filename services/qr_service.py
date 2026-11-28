"""
services/qr_service.py

What goes on a product sticker: a QR code and a Code 128 bar code, both carrying the
product's code (SKU), which never changes. No Qt in here; services/label_render.py paints.

The QR is error-correction level H (a quarter to a third of it can be hidden), so the
Vriksha mark can sit in the middle and it still scans.
"""

import os

import segno
from barcode import Code128
from barcode.errors import BarcodeError

# When the shop has a public product page, set this (for example https://shop.example/p) and
# the QR opens that page; until then the QR holds "VS:<code>", which the staff app reads.
QR_BASE_URL = os.environ.get("VRIKSHA_QR_BASE_URL", "").rstrip("/")
LOGO_FRACTION = 0.22  # the logo's width as a part of the QR's width (a safe limit is about 0.30)


def qr_payload(sku: str) -> str:
    return f"{QR_BASE_URL}/{sku}" if QR_BASE_URL else f"VS:{sku}"


def sku_from_payload(text: str) -> str:
    """The product code out of a scanned QR or bar code (the staff app and the counter use it)."""
    text = (text or "").strip()
    if QR_BASE_URL and text.startswith(QR_BASE_URL + "/"):
        return text[len(QR_BASE_URL) + 1:]
    return text[3:] if text.startswith("VS:") else text


def qr_matrix(sku: str) -> list[list[int]]:
    """Rows of 0/1 (1 = dark), no quiet zone."""
    return [list(row) for row in segno.make(qr_payload(sku), error="h", boost_error=False).matrix]


def barcode_bars(sku: str) -> str:
    """Code 128 as a string of 1 (bar) and 0 (space), one character per module; empty when the code
    has letters Code 128 cannot hold (the label then carries the QR alone)."""
    try:
        return Code128(sku).build()[0]
    except BarcodeError:
        return ""
