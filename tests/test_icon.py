"""The program icon ships and is wired into the build."""

from pathlib import Path

from PyQt6.QtGui import QIcon

from ui.assets import icon_path

ROOT = Path(__file__).resolve().parent.parent


def test_the_icon_has_every_size_windows_asks_for(qapp):
    assert icon_path().is_file()
    sizes = sorted(s.width() for s in QIcon(str(icon_path())).availableSizes())
    assert sizes == [16, 24, 32, 48, 64, 128, 256]


def test_the_build_and_installer_use_it():
    bs = chr(92)
    build = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
    iss = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert f"--icon assets{bs}icon{bs}vriksha.ico" in build
    assert '--add-data "assets/icon;assets/icon"' in build
    assert f"SetupIconFile=..{bs}assets{bs}icon{bs}vriksha.ico" in iss
