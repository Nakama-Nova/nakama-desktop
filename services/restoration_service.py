"""
services/restoration_service.py

Temple restorations (owner and artisans only): projects, the photos/video scans taken
for them, and the 3D files the workshop PC builds. Big transfers stream from/to disk
and report progress, and use quiet=True so they are safe to run on a worker thread
(a pop-up from a non-GUI thread would crash Qt).
"""

import os
from pathlib import Path
from typing import Callable

from services import api_client
from services.api_client import APIClient
from services.session import Session

MB = 1024 * 1024
MIN_PHOTOS, MAX_PHOTOS = 8, 300
PHOTO_MAX, VIDEO_MAX = 100 * MB, 1024 * MB
PHOTO_EXT, VIDEO_EXT = {".jpg", ".jpeg", ".png"}, {".mp4", ".mov"}
CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".mp4": "video/mp4", ".mov": "video/quicktime"}

STATUSES = [
    ("Planned", "planned"),
    ("Capturing", "capturing"),
    ("Building 3D model", "processing"),
    ("Ready to review", "review"),
    ("Carving", "carving"),
    ("Finishing", "finishing"),
    ("Painting", "painting"),
    ("Restored", "restored"),
    ("On hold", "on_hold"),
    ("Cancelled", "cancelled"),
]
STATUS_WORDS = {value: label for label, value in STATUSES}
KIND_WORDS = {"glb": "3D model (.glb)", "stl": "3D print/CNC mesh (.stl)", "obj": "3D model (.obj)", "ply": "3D scan (.ply)", "nc": "CNC G-code (.nc)", "render": "Preview picture"}
SCAN_WORDS = {"created": "Uploading", "uploaded": "Waiting for the workshop PC", "processing": "Building 3D model", "done": "Done", "failed": "Failed", "cancelled": "Cancelled"}


def check_capture(kind: str, paths: list[str]) -> str | None:
    """A plain-words problem with the chosen files, or None. Mirrors the server's rules."""
    if not paths:
        return "Choose the files first."
    exts, biggest = (PHOTO_EXT, PHOTO_MAX) if kind == "photos" else (VIDEO_EXT, VIDEO_MAX)
    if kind == "video" and len(paths) != 1:
        return "Choose one video."
    if kind == "photos" and len(paths) < MIN_PHOTOS:
        return f"Take at least {MIN_PHOTOS} photos, walking all the way around the piece."
    if len(paths) > MAX_PHOTOS:
        return f"At most {MAX_PHOTOS} photos in one scan."
    for p in paths:
        if Path(p).suffix.lower() not in exts:
            return f"{Path(p).name}: use {', '.join(sorted(exts))} files for {kind}."
        if os.path.getsize(p) > biggest:
            limit = "100 MB a photo" if kind == "photos" else "1 GB for a video"
            return f"{Path(p).name} is too big (limit {limit})."
    return None


class _Reader:
    """A file that counts the bytes as they are sent (requests uses __len__ and read)."""

    def __init__(self, path: str, on_bytes: Callable[[int], None]):
        self._f, self._n, self._on = open(path, "rb"), os.path.getsize(path), on_bytes

    def __len__(self):
        return self._n

    def read(self, size=-1):
        chunk = self._f.read(size)
        if chunk:
            self._on(len(chunk))
        return chunk

    def close(self):
        self._f.close()


class RestorationService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    # -- projects ------------------------------------------------------
    def projects(self, status: str | None = None) -> list:
        return self._api._get("/restorations", self._t(), params={"status": status}) or []

    def project(self, restoration_id: str) -> dict:
        return self._api._get(f"/restorations/{restoration_id}", self._t())

    def team(self) -> list:
        return self._api._get("/restorations/team", self._t()) or []

    def create(self, data: dict) -> dict:
        return self._api._post("/restorations", self._t(), json=data)

    def update(self, restoration_id: str, data: dict) -> dict:
        return self._api._patch(f"/restorations/{restoration_id}", self._t(), json=data)

    # -- capture: photos or one video -> the workshop PC ------------------
    def upload_capture(self, restoration_id: str, kind: str, paths: list[str], params: dict, progress: Callable[[int, int, str], None]) -> dict:
        """Create the scan, send every file straight to the store, then queue it."""
        problem = check_capture(kind, paths)
        if problem:
            raise ValueError(problem)
        t = self._t()
        scan = self._api._post("/scans", t, json={"restoration_id": restoration_id, "source_kind": kind, "params": params}, quiet=True)
        specs = [{"filename": Path(p).name, "content_type": CONTENT_TYPES[Path(p).suffix.lower()], "size": os.path.getsize(p)} for p in paths]
        signed = self._api._post(f"/scans/{scan['id']}/presign", t, json={"files": specs}, quiet=True)["files"]
        total, sent = sum(s["size"] for s in specs), [0]

        def count(n):
            sent[0] += n

        for i, (path, target) in enumerate(zip(paths, signed)):
            reader = _Reader(path, lambda n: (count(n), progress(sent[0], total, f"Uploading {i + 1} of {len(paths)}")))
            try:
                r = api_client._send(target["method"].lower(), target["url"], fast_fail=False, data=reader, headers=target["headers"], timeout=api_client.UPLOAD_TIMEOUT)
            finally:
                reader.close()
            if r.status_code not in (200, 201, 204):
                raise RuntimeError(f"Upload of {Path(path).name} failed ({r.status_code}). Check the connection and try again.")
        return self._api._post(f"/scans/{scan['id']}/complete", t, json={"keys": [s["key"] for s in signed]}, quiet=True)

    # -- results -------------------------------------------------------
    def download_file(self, restoration_id: str, file_id: str, dest: str, progress: Callable[[int, int, str], None]) -> str:
        """Save one result to `dest`. Returns the path."""
        link = self._api._get(f"/restorations/{restoration_id}/files/{file_id}/download", self._t(), quiet=True)
        total = int(link.get("size_bytes") or 0)
        done = 0
        r = api_client._send("get", link["url"], fast_fail=False, stream=True, timeout=(10, 300))
        if r.status_code != 200:
            raise RuntimeError(f"Download failed ({r.status_code}). Try again.")
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                progress(done, total or done, "Saving")
        return dest
