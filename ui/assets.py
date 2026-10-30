"""
ui/assets.py

Finds and loads the brand images that ship in assets/images: the Vriksha logo and the
wood-carving cut-outs (transparent background, photographed facing right). Works from
source and from the PyInstaller build, which unpacks assets/ next to the program.
"""

import atexit
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QImage, QPixmap

IMAGE_DIR = Path(__file__).resolve().parent.parent / "assets" / "images"


def logo_path(short: bool = False) -> Path:
    """The brand logo (tree + STUDIO), or the short VS mark."""
    return IMAGE_DIR / "brand" / ("logo-vs.png" if short else "logo.png")


def carving_path(name: str) -> Path:
    return IMAGE_DIR / "carvings" / f"{name}.webp"


@lru_cache(maxsize=None)
def load_image(path: Path, mirrored: bool = False) -> QImage:
    """The image from disk (cached); null image if the file is missing, so the screens
    simply show no picture rather than failing."""
    image = QImage(str(path))
    return image.mirrored(True, False) if mirrored and not image.isNull() else image


def clear_caches() -> None:
    """Drop the cached images. QPixmaps must be freed while the Qt application still
    exists, so this runs when the app quits and again at interpreter exit."""
    scaled_pixmap.cache_clear()
    load_image.cache_clear()


atexit.register(clear_caches)
_hooked = False


def _hook_app_quit() -> None:
    global _hooked
    app = QCoreApplication.instance()
    if app is not None and not _hooked:
        _hooked = True
        app.aboutToQuit.connect(clear_caches)


@lru_cache(maxsize=256)
def scaled_pixmap(path: Path, height_px: int, mirrored: bool, dpr: float) -> QPixmap:
    """The image scaled to `height_px` logical pixels tall, sharp at device pixel ratio
    `dpr` (high-DPI screens get more pixels, not a blurry upscale)."""
    _hook_app_quit()
    source = load_image(path, mirrored)
    if source.isNull() or height_px <= 0:
        return QPixmap()
    pixmap = QPixmap.fromImage(
        source.scaledToHeight(
            max(1, round(height_px * dpr)), Qt.TransformationMode.SmoothTransformation
        )
    )
    pixmap.setDevicePixelRatio(dpr)
    return pixmap
