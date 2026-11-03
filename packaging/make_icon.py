"""
Builds assets/icon/vriksha.ico from the brand logos: the Vriksha tree on a cream rounded
square, and the short VS mark for the small sizes where the tree turns to mush.

    python packaging/make_icon.py

Run it after changing a logo, then commit the .ico (the build uses the committed file).
Needs only PyQt6. Entries below 256px are 32-bit bitmaps and the 256px one is PNG, the
form every Windows version since Vista reads.
"""

import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "images" / "brand"
OUT = ROOT / "assets" / "icon" / "vriksha.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SMALL = 32  # up to this size the VS mark is used
CREAM = QColor("#FBF6EC")
RIM = QColor("#E8DCC8")


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    r = size * 0.2
    inset = max(0.5, size * 0.02)
    body = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    path = QPainterPath()
    path.addRoundedRect(body, r, r)
    p.fillPath(path, CREAM)
    p.setPen(RIM)
    p.drawPath(path)
    logo = QImage(str(BRAND / ("logo-vs.png" if size <= SMALL else "logo.png")))
    pad = size * (0.12 if size <= SMALL else 0.1)
    box = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    scaled = logo.scaled(
        int(box.width()), int(box.height()), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    p.drawImage(int(box.x() + (box.width() - scaled.width()) / 2), int(box.y() + (box.height() - scaled.height()) / 2), scaled)
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def dib_bytes(img: QImage) -> bytes:
    """A 32-bit bitmap entry: header, pixels bottom row first, then an (unused) AND mask."""
    w, h = img.width(), img.height()
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rgba = img.convertToFormat(QImage.Format.Format_ARGB32)
    rows = []
    for y in range(h - 1, -1, -1):  # BGRA, which is what ARGB32 is on little-endian machines
        rows.append(bytes(rgba.constScanLine(y).asarray(w * 4)))
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)
    return header + b"".join(rows) + mask


def build() -> bytes:
    entries = []
    for s in SIZES:
        img = render(s)
        entries.append((s, png_bytes(img) if s >= 256 else dib_bytes(img)))
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for s, data in entries:
        out += struct.pack("<BBBBHHII", 0 if s >= 256 else s, 0 if s >= 256 else s, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in entries:
        out += data
    return bytes(out)


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
