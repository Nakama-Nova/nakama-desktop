# Desktop edge-case checklist

Tick each one by hand before a release, or point to the test that covers it. `[x]` = a test exists today.

## Network
- [x] Server not running at startup: main window opens, every page builds (`test_offline_startup.py`).
- [x] A sale made offline lands in the outbox and is pushed later (`test_offline_billing.py`).
- [x] A read whose link drops is repeated once, a write never is (`test_hardening.py`).
- [ ] Wi-Fi drops in the middle of a push: nothing is lost, nothing is sent twice (the backend dedupes by client id).
- [ ] Connection returns: the next call goes through within 10s (`OFFLINE_PAUSE`), and sign-in tries at once.
- [ ] Server answers slowly (over 30s): a "Server not answering" dialog, and the screen stays usable.
- [ ] Server returns HTML or an empty body with status 200 or 502: no crash, a readable message.
- [ ] Upload of a large photo or 3D file over a weak link: times out at 120s with a message, no half-saved record.

## Session
- [x] Token rejected (401): one sign-out dialog even when many background calls fail together (`test_session_expiry.py`).
- [ ] Password changed on another PC: this PC is signed out on its next call, with an explanation.
- [ ] Password changed here: the new token is kept and the next screen load works.
- [ ] Role changed by the owner while the user is signed in: the next 403 shows a dialog, the sidebar updates after the next sign-in.
- [ ] Credential store unavailable (`keyring` fails): the app starts and signs in, it just does not remember the session.

## Local storage
- [ ] `data/nakama_local.db` deleted: it is recreated, a full pull restores the data.
- [x] `data/nakama_local.db` corrupted (random bytes): kept aside as `.damaged-<time>.db`, a fresh one is started (`test_hardening.py`).
- [ ] Read-only program folder (installed build): data lives under `%LOCALAPPDATA%\VrikshaStudios` (`main.py`).
- [ ] Disk full while writing the outbox: the sale is refused with a message, not silently dropped.
- [ ] Two copies of the app open on one PC: second one does not corrupt the database.

## Data and payloads
- [ ] Item with no image, no price, a very long name: tables and dialogs do not break the layout.
- [ ] Numbers as strings (`"12.50"`), nulls where a number was expected: screens show a dash, not a traceback.
- [ ] Unknown enum value from a newer backend (`status` not in the app's word list): shown as raw text.
- [ ] Dates in the past, future, and timezone-aware strings: parse without error (`parse_date`).
- [ ] 422 from the backend: the message names the field.
- [ ] Pagination or 10,000 rows: the screen still opens in under a second (`test_speed.py` is the baseline).

## Desktop behaviour
- [ ] Window shrunk to 1024x600 and maximised on a 4K screen with 150% scaling: no clipped buttons or hidden columns.
- [ ] Close the window mid-load: background threads end, no error on exit.
- [ ] Double-click Save: one record, not two.
- [ ] Tab through a dialog: order is top to bottom, Enter submits, Esc cancels.
- [ ] Print or save a bill with no printer or a read-only folder: clear message.

## Roles
- [x] Each role sees only its sidebar entries (`test_pricing_ui.py`, `test_places_machines_budgets.py`).
- [ ] A hidden screen opened by a stale link or direct call returns 403 and a dialog, not data.
