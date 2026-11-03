# Vriksha Studios Desktop (NakamaDesk)

The PyQt6 staff desk for **Vriksha Studios** (FurniBiz ERP): billing, stock, orders, workshop and money screens on one Windows PC. It talks to [nakamadesk-backend](https://github.com/Nakama-Nova/nakamadesk-backend) over HTTP and keeps working when the connection drops.

---

## What it does

The sidebar groups the screens, and each one shows only what the signed-in role may use (the server enforces the same rules).

| Section | Screens |
|---|---|
| Selling | New Bill, Bill History, Orders, Buyers, Letters |
| Stock and buying | Stock, Materials, Purchases, Places |
| Workshop | 3D Lab, Restoration, Designs, Machines and tools |
| People and pay | Attendance, Wages, Staff |
| Money | Expenses, Profit, Budgets, Reports |

Plus a Home dashboard, notifications, and in-app updates (below).

**Offline.** A counter sale made with no server is saved in a local SQLite outbox (`data/nakama_local.db`) and pushed to `POST /sync/push` by a background sync every 60 seconds, in batches of 200. The server numbers the bill, so a printable bill appears only after the sale syncs. Pages show the last data they have, or an empty state, when the server is down. Other offline writes and a full local read cache are not built yet; see [docs/DESKTOP_BLUEPRINT.md](docs/DESKTOP_BLUEPRINT.md) for what is and is not covered.

**Sign-in.** The token and role are kept in the Windows credential store (`keyring`), not in a file, and the token's expiry is checked when the app reopens.

## Tech

PyQt6, `requests`, `python-dotenv`, `keyring`, SQLite. Python 3.12 is what CI and the installer use.

```text
main.py          entry point
ui/              screens, dialogs, theme, fonts
services/        one module per backend area, plus API client, session, sync, event bus
database/        local SQLite database and the outbox
tests/           headless pytest suite
packaging/       PyInstaller build and Inno Setup installer
docs/            blueprint, edge-case checklist, screenshots
```

Screens call a service, never `requests` directly. Services share one `APIClient` (`services/api_client.py`), and an event bus refreshes other screens when data changes (a sale updates the dashboard).

---

## Run from source

You need Python 3.12 and a running backend (see its README, or use the shop's server).

```bash
git clone https://github.com/Nakama-Nova/nakama-desktop.git
cd nakama-desktop
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` next to `main.py`:

```env
API_BASE_URL=http://127.0.0.1:8000
```

```bash
python main.py
```

Running from source keeps the local database in `./data`. The installed program keeps it in `%LOCALAPPDATA%\VrikshaStudios`.

Note: `requirements.txt` is saved as UTF-16 (a Windows PowerShell habit). `pip` reads it fine; some other tools show it as binary.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

The suite runs the real Qt widgets headless, with the server unreachable, in a temporary folder and with the keyring disabled, so it never touches real data or saved logins. `tests/test_backend_live.py` is the only one that talks to a server: it needs `NAKAMA_TEST_URL`, `NAKAMA_TEST_USER` and `NAKAMA_TEST_PASS`, and is skipped without them. CI (`.github/workflows/desktop-ci.yml`) runs the tests plus a flake8 check for syntax errors and undefined names only; the code is not yet style-clean. [docs/EDGE_CASES.md](docs/EDGE_CASES.md) is the checklist to tick by hand before a release.

---

## Windows installer

CI builds `VrikshaStudiosDesk-Setup-<version>.exe` for every pull request (Actions run, then *Artifacts*), and attaches it to a GitHub Release when a tag like `v1.0.0` is pushed. A `.sha256` file sits next to it.

- Installs for the current user only (no administrator password) and asks once for the server address.
- Shop data (local database, invoices, server address) is kept in `%LOCALAPPDATA%\VrikshaStudios`, and survives upgrades and uninstalling. To change the server later, edit `API_BASE_URL` in the `.env` file there.
- **Updates:** this repository is private, so the installed program asks the shop's own server (signed in as the staff member) for the newest release a few seconds after it starts and every 6 hours; the server reads the private GitHub Releases for it (the token is set up as described in the backend's `docs/ONBOARDING.md`). When a newer version is published it shows a banner (and a Windows notification if the window is behind other programs). **Update now** downloads the installer through the server, checks its SHA-256, runs it silently and the app reopens by itself; nothing installs without that click. The sidebar's *Updates* button checks on demand. Development copies and branch builds never prompt.
- The installer is **not code-signed**, so Windows SmartScreen shows "Unknown publisher" the first time: choose *More info, Run anyway*. A signing certificate is the only fix and is a paid extra.
- Build it locally: `pip install -r requirements.txt -r requirements-build.txt`, then `./packaging/build.ps1`, then `ISCC /DAppVersion=1.0.0 packaging\installer.iss` (needs Inno Setup 6).

---

## Licence

This is **proprietary software**. Copyright (c) 2026 Nakama Nova, all rights reserved. It may not be copied, modified or shared; see `LICENSE` (it is also shown when the installer runs). To report a security problem, see `SECURITY.md`.

Third-party components keep their own licences, which are installed with the program (`THIRD_PARTY_LICENSES.txt`).

**Distribution note:** the program uses PyQt6, which is available under the GPL v3 or a commercial licence from Riverbank Computing. Keep it inside the owner's own business until one of those is settled (a commercial PyQt licence, or moving the app to PySide6, which is LGPL).
