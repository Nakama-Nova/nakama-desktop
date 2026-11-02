# Nakama Desktop: production blueprint

Written 2026-11-02 from the code in `nakama-desktop` (this branch) and `nakamadesk-backend` (`origin/main`).
✅ = checked in the code. ⚠️ = a gap or a decision still open.

## 1. Architecture (backend audit)

**Backend** (FastAPI, SQLAlchemy, Postgres): JWT HS256 bearer tokens, `POST /auth/login` (form fields),
`GET /auth/me`, about 144 routes across `app/api/*` (items, sales, orders, stock, places, machines and tools,
budgets, attendance, expenses, finance, designs, lab, letters, public, sync…). One deployment serves one
business (ADR-0001). Offline writes go through `POST /sync/push` (idempotent by client id, at most 500
operations) and `GET /sync/pull` (last write wins, tombstones). Changing a password returns a fresh token
(`token_version`), which the desktop now stores.

**Desktop** (PyQt6, Python):

| Layer | Where | Job |
|---|---|---|
| API client | `services/api_client.py` | One shared `requests.Session`; timeouts (5s connect, 30s read, 120s upload, 10s login); after a failed connect, further calls fail at once for 10s (`OFFLINE_PAUSE`); 401 raises `SessionExpiredError` once and signs the user out; 403 raises `ForbiddenError`. |
| Services | `services/*_service.py` | Thin wrappers per area. No UI imports. |
| Session | `services/session.py` | Token and role held in memory and in the OS credential store (`keyring`). |
| Offline | `database/local_db.py`, `outbox_repository.py`, `services/sync_service.py` | SQLite file `data/nakama_local.db`; outbox of sales, items, attendance, raw materials, pushed in batches of 200. |
| UI | `ui/*.py`, `ui/components/*` | Screens load in the background (`ui/workers.py`: `load_async`) so the window never freezes. |

**Framework choice: stay on PyQt6.** Reasons: the app is built, 451 tests cover it, it runs on one
shop PC, and a rewrite (Tauri, Electron, .NET) would cost more than everything it could fix. Revisit only
if you need macOS or Linux installers, or a web version of the same screens.

**Security and data**
- ✅ Token stored in Windows Credential Manager, not in a file or `.env`.
- ✅ `insecure_remote()` flags plain `http://` to a server outside the shop network.
- ✅ Role checks in the UI mirror the backend; the backend is the real gate (403 becomes a plain dialog).
- ⚠️ The local SQLite file is not encrypted. It holds sales and customer rows. Acceptable on one locked
  shop PC; add SQLCipher or Windows disk encryption (BitLocker) if the PC leaves the shop.
- ✅ A GET whose connection dropped mid-way is repeated once. Writes are never repeated, and a server that
  cannot be reached at all still fails at once (`OFFLINE_PAUSE`), so screens stay responsive.
- ✅ A damaged local database is kept aside as `nakama_local.damaged-<time>.db` and a fresh one is started.

## 2. Layout and design tokens

**Layout:** left sidebar grouped under headings (Stock and buying, Workshop, Money…) filtered by role,
content area on the right, 12-column card grid (`Grid12`) that reflows by window width. Tables stretch to the
window. List screens follow one pattern: header with title and actions, filter chips with counts, live search,
table, double-click for detail.

**Tokens** (`ui/theme.py`): brand brown `#5A2A06`, gold `#BF830B`, success `#2F7D4F`, danger `#B3261E`;
Cormorant Garamond for headings and Inter for text (bundled in `assets/fonts`, falls back to Georgia and
Segoe UI); spacing 4/8/16/24; 6px radius controls.

| Item | Status |
|---|---|
| Light theme | ✅ |
| Dark theme | ⚠️ not built. Needs every `Colors.*` use to go through a theme object; plan it as one change. |
| Keyboard shortcuts | ✅ F5 refresh, Ctrl+F search box, Ctrl+1…9 first nine sidebar entries (`MainWindow._install_shortcuts`). ⚠️ Ctrl+N (new) is not added; each screen's "add" button differs. |
| Contrast (WCAG AA, 4.5:1) | ✅ text colours measured and a test keeps them at 4.5:1 on every surface. Muted text, amber and green were darkened. `BRAND_GOLD` is for borders and fills only, not small text. |
| Focus outlines and tab order | ⚠️ not audited. |
| Text size | Fixed pixel sizes. Windows display scaling works; there is no in-app zoom. |

## 3. UI states every screen needs

| State | How it shows today |
|---|---|
| Loading | `load_async` runs the fetch off the GUI thread; the screen keeps its last data and a refresh button stays live. |
| Empty | `EMPTY_STATES` in `ui/main_window.py` gives each page an icon and a sentence plus what to do next. |
| Success | Table or cards filled; confirmation dialogs name what was done. |
| Offline | Reads show the last data or an empty state; sales go to the outbox; the sync status in the title area says what is waiting. |
| 401 | One dialog ("signed out"), then the login window; later 401s from background jobs stay silent. |
| 403 | `@handle_permissions` shows "Permission denied" naming the action. |
| 409 | Plain-language dialog (for example "in use"). |
| 5xx or timeout | "Server not answering" or "No connection" dialog from the global exception hook in `main.py`. |
| Validation (422) | `APIError._plain` turns the server detail into one readable line. |

## 4. Production checklist

- [ ] `API_BASE_URL` points to an `https://` host (the app warns on plain remote http).
- [ ] Installer build runs the full suite first (`pytest -q`).
- [ ] First-run path tested with no `.env`, no `data/` folder, no network.
- [ ] Backup of `%LOCALAPPDATA%\VrikshaStudios\data` is part of the shop's routine.
- [ ] Update check (`services/update_service.py`) points at the release URL and is tested with a fake newer version.
- [ ] Remaining design gaps above are accepted or scheduled.
