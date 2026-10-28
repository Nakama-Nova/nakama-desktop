"""
services/sculpture_service.py

The 3D model of a sculpture in Stock: find the models the workshop PC built from its
photos and save one to open. (Starting the scan itself is RestorationService.upload_item_capture.)
"""

from typing import Callable

from services import api_client
from services.api_client import APIClient
from services.session import Session


class SculptureService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def models(self, item_id: str) -> list:
        """The sculpture's .glb models, oldest first (the last is the newest)."""
        files = self._api._get(f"/items/{item_id}/assets", self._t(), quiet=True) or []
        return [a for a in files if a.get("kind") == "glb"]

    def download(self, item_id: str, asset_id: str, dest: str, progress: Callable[[int, int, str], None]) -> str:
        """Save one file to `dest`. The server answers with a short-lived signed link."""
        url = f"{self._api._base_url}/items/{item_id}/assets/{asset_id}/download"
        r = api_client._send("get", url, fast_fail=False, headers=self._api._headers(self._t()), stream=True, timeout=(10, 300))
        if r.status_code != 200:
            raise RuntimeError(f"Download failed ({r.status_code}). Try again.")
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                progress(done, total or done, "Saving the model")
        return dest
