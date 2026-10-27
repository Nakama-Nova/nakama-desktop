"""
services/version.py

The version this program was built as. CI overwrites APP_VERSION from the release
tag (v1.2.3 -> "1.2.3") before packaging; in the repo it stays a development
marker, so running from source never offers an update.
"""

import re
import sys

APP_VERSION = "0.0.0-dev"

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """'v1.2.3' or '1.2.3' -> (1, 2, 3). Anything else (dev builds, tags like v1.2) -> None."""
    m = _VERSION.match((text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_release_build() -> bool:
    """True only for the installed program built from a release tag."""
    parsed = parse_version(APP_VERSION)
    return bool(getattr(sys, "frozen", False)) and parsed is not None and parsed != (0, 0, 0)
