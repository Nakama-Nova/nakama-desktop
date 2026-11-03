"""
ui/components/place_picker.py

A drop-down to choose where something happens: which place a bill is sold from, which
place a stock count or change applies to. The last choice is remembered for the next time,
so a counter that always sells from one place never has to pick it again.

    picker = PlacePicker("sale")
    picker.set_places(places)          # the list from PlacesService.places()
    picker.place_id()                  # the chosen id, or None for "no particular place"
"""

import requests
from PyQt6.QtWidgets import QComboBox

from services.api_client import APIError
from services.places_service import PlacesService
from ui.theme import Theme

NO_PLACE = "No particular place"
_last: dict[str, str] = {}  # purpose -> place id chosen last time, for this run of the program


def active(places: list) -> list:
    return [p for p in places if p.get("is_active", True)]


def selling_places(places: list) -> list:
    """Places that can sell at a counter: those with a till, or a shop."""
    return [p for p in active(places) if p.get("has_till") or p.get("kind") == "shop"]


def fetch_places() -> list | None:
    """The active places, or None when they could not be read (offline, or not allowed).
    A screen that cannot read them carries on without asking, never fails."""
    try:
        return active(PlacesService().places())
    except (requests.RequestException, APIError):
        return None


class PlacePicker(QComboBox):
    def __init__(self, purpose: str, parent=None):
        super().__init__(parent)
        self._purpose = purpose
        self.setStyleSheet(Theme.input_style())
        self.currentIndexChanged.connect(self._remember)

    def set_places(self, places: list, allow_none: bool = False) -> None:
        """Fill the list. The remembered place is chosen again; failing that the only shop is,
        failing that (with allow_none) "No particular place"."""
        self.blockSignals(True)
        self.clear()
        if allow_none:
            self.addItem(NO_PLACE, None)
        for p in places:
            self.addItem(p["name"], str(p["id"]))
        remembered = self.findData(_last.get(self._purpose))
        shops = [p for p in places if p.get("kind") == "shop"]
        if remembered >= 0:
            self.setCurrentIndex(remembered)
        elif len(shops) == 1:
            self.setCurrentIndex(self.findData(str(shops[0]["id"])))
        else:
            self.setCurrentIndex(0)
        self.blockSignals(False)

    def place_id(self) -> str | None:
        return self.currentData()

    def _remember(self, _index: int) -> None:
        if self.currentData():
            _last[self._purpose] = self.currentData()
