# Plan: product QR codes, proper billing, proper HR (24 Nov 2026)

Planning only. No feature code is written. You decide what to build and in what order.

Basis: the desktop code on `main` (5789826). The backend (`nakamadesk-backend`) is a separate repo and was **not** available to read here, so every "backend needs" line below is inferred from what the desktop calls and receives. Check each one against the backend before building (the 23 Nov review made the same caveat).

Effort figures are developer-days for one person who knows the codebase, including tests. They are estimates, not promises.

---

## 0. Summary

| Upgrade | What exists today | Biggest gaps | Backend change? | Effort |
|---|---|---|---|---|
| 1. Product QR | Nothing. No QR library, no printing code at all in the desktop. | Everything. 3D link needs a permanent public URL. | Small (one public product page + optional public 3D link) | 6-9 days |
| 2. Billing | Counter sale, server-numbered invoice, GST (CGST/SGST), PDF from server, reprint, payment edit afterwards, offline queue. Orders have multi-payment. | No discount at sale, no payment taken at sale, no split payment, no returns/credit notes, PDF only one format, offline bills have no number or PDF. | Yes, most items | 15-22 days |
| 3. HR | Staff accounts, daily wage, check-in/out with on-site check, payroll (piece/overtime/bonus/advance, pay-out). | No leave, shifts, holidays, documents, salary history, payslips, own-pay view. | Yes, most items | 14-20 days |

Suggested order: **QR first** (self-contained, visible win), then **Billing phase B1-B2** (money correctness), then **HR H1-H2**, then the rest. QR and the two later phases do not touch the same files, so they can run in parallel if you want two sessions.

---

## 1. Product QR codes with the Vriksha logo

### 1.1 What is in the code today

- Products are shown in `ui/inventory_window.py` (Stock). Each row has actions built in `_actions` (line ~241), including 3D scan and View 3D (`_scan_3d`, `_view_3d`, which use `ui/item_scan.py`). Products have `id` (UUID) and `sku` (given by the server, never changes: `ui/item_form.py:66`).
- 3D today: `view_3d()` downloads the newest `.glb` of the item (`SculptureService.models`) and opens it in the PC's 3D viewer. The 3D Lab (`ui/lab_screen.py`, `services/lab_service.py`) asks the backend for a **short-lived** link (`create_lab_link`) and opens it in the browser.
- Logo: `assets/images/brand/logo.png` (tree + STUDIO, wide) and `logo-vs.png` (short VS mark, 81 KB). `ui/assets.py` has `logo_path(short=True)` and `load_image()` which already works from source and from the PyInstaller build.
- Printing: **there is none in the desktop.** Bill and letter PDFs are made by the backend, saved to `%LOCALAPPDATA%\VrikshaStudios\invoices`, and opened with `os.startfile` (`services/sales_service.py`, `services/letters_service.py`). No `QPrinter`, `QPdfWriter` or `QPrintDialog` anywhere.
- Libraries: `requirements.txt` has PyQt6 6.10.2 and requests; **no QR library, and no Pillow** (Pillow happens to be on this PC but is not listed, so a build would not include it).

### 1.2 What the QR encodes

Two kinds of code per product. Both are short, because short codes have bigger squares and scan better on a small sticker.

1. **Product code (the main one, 2D label).** A web address, not raw text:
   `https://<shop-domain>/p/<SKU>` (for example `https://vrikshastudios.in/p/VS-00123`).
   - Phone camera opens the product page (photo, price, "ask on WhatsApp").
   - The desktop POS can read the same code with a USB barcode/QR scanner and take the SKU after `/p/` to add the item to the bill. One code serves customers and staff.
   - The SKU never changes, so a printed sticker stays valid for the life of the piece. Do **not** encode the price, the stock count or the UUID.
2. **3D code (items that have a scanned model).** `https://<shop-domain>/p/<SKU>/3d` which opens a page with the model viewer (and AR on phones if you want it later).
   - The existing Lab link cannot be used: it expires and is meant for staff.
   - The `.glb` download is login-protected, so a customer's phone cannot fetch it. **This needs the backend** (see 1.6).

Fallback if you do not want a public page yet: the QR holds `VS:<SKU>` plain text. Staff scanners work, customers' phones show text only. Cheap, but it throws away most of the value; I do not recommend it except as a stop-gap.

### 1.3 Logo in the centre without breaking the scan

- Library: **`segno`** (pure Python, no dependencies, about 100 KB). It gives the module matrix; we paint it ourselves with `QPainter`, so the output is vector-quality at any print size, and we need no Pillow. The usual alternative, `qrcode` + Pillow, pulls in a heavier image stack and PyInstaller size for nothing we need. Add one line to `requirements.txt` and `requirements-build.txt` and check `packaging/build.ps1` bundles it.
- **Error correction level H** (recovers up to about 30 % damage). A logo hides modules, so we must use H; L/M would fail.
- Logo size: **about 22 % of the QR width** (roughly 5 % of the area; the safe ceiling is about 30 % of width). Use the short VS mark (`logo-vs.png`); the full tree + STUDIO logo is too wide and too detailed at 1-2 cm. Put the logo on a white square with a small margin (clear the modules under it, do not draw over them).
- Keep the data short (SKU URL, QR version 3-4 at level H, about 29-33 modules per side) so each module stays printable. Quiet zone: 4 modules of white around the code (the standard).
- Colours: dark brown on white would scan fine, but **keep modules near-black** (contrast matters more than brand colour on laser and thermal printers). The brand shows through the logo and the label text, not the code.
- **Always test-scan**: a small automated check decodes the generated code (we can verify the matrix round-trips by regenerating it from the data, and a real phone check on first print). Reject (and fall back to a smaller logo) if the logo covers more than the limit.

### 1.4 Print formats

All are drawn by one routine that paints a label onto a `QPainter`, so the same code feeds the PDF and the printer. Sizes are millimetres.

| Format | Size | Contents | Printer |
|---|---|---|---|
| Single label (small) | 50 x 25 | QR (22 mm) + SKU + short name + price | Thermal label printer (or any) |
| Single label (large) | 60 x 40 | QR + name + SKU + price incl. GST + wood/size | Thermal or laser |
| Thermal roll 58 mm / 80 mm | 58 or 80 wide, length auto | One label per product, optional cut line | Receipt/thermal printer |
| Hang tag | 50 x 90 with a hole mark | Logo on top, product name, QR, price, SKU, "Made by hand at Vriksha Studios" | Laser/inkjet on card stock, cut by hand |
| Sticker sheet | A4, common layouts (21-up 63.5 x 38.1; 65-up 38.1 x 21.2; 24-up 63.5 x 33.9) | QR + SKU + price | Laser/inkjet, label sheets |
| A4 grid / catalogue sheet | A4, 3 x 4 or 4 x 6 | QR + name + SKU, no price (for catalogues, shelf cards) | Any |
| 3D QR card | A6 or 60 x 60 | 3D code + "Scan to see it in 3D" + logo | Any |

Options on the print dialog: which products (checkboxes in Stock, or "all in a category"), copies per product, **start at position N** on a sheet (so a half-used sticker sheet is not wasted), show price yes/no, 2D or 3D code, and a **preview** before printing.

How it prints: build a PDF with `QPdfWriter` (a `QtGui` class, no new package) and open it the same way bills are opened (`SalesService.open_pdf` pattern), **or** send straight to a chosen printer with `QPrinter` / `QPrintDialog` from `PyQt6.QtPrintSupport` (ships in the PyQt6 wheel already pinned). PDF-first is safer: it works with any printer driver and gives you something to check. Thermal printers need their page size set to the label (the Windows driver usually exposes it); document that setup once in the README.

### 1.5 Where it lives in the app

- New `services/qr_service.py`: build the URL for a product, make the QR matrix, return a `QImage`/paint onto a painter. No Qt widgets, easy to test.
- New `services/label_layouts.py`: the table of formats above (width, height, grid, margins). Adding a format is one dict entry.
- New `ui/label_print_dialog.py`: the options and preview.
- `ui/inventory_window.py`: a **"Labels"** button in the header (print for the ticked or filtered products) and a small "QR" action per row. Permission: `Session.can("items:item:read")` (anyone who can see stock can print a label; no new permission needed). The 3D option is shown only when `SculptureService.models(item_id)` returns something.
- Tests: label layout maths (positions fit the page), QR round trip, "no 3D model → no 3D option".

### 1.6 Backend needs

1. **Public product page** `GET /p/<sku>`: name, photo, price, availability. The website seems to exist (orders have `source: web`, `site:content:manage`), so this may be a page on the website that reads the existing product API. Need to confirm which domain the codes will point at.
2. **Public 3D page** `GET /p/<sku>/3d` plus a way for a customer's phone to fetch the model **without a login** (a public, read-only, opt-in flag per product, or a signed link that does not expire). Needed only for the 3D variant.
3. Optional: `GET /items/by-sku/<sku>` for the scanner lookup at the counter, if it is not already there (the desktop can also look the SKU up in its cached item list, which is offline-friendly).

### 1.7 Phases

| Phase | Work | Effort |
|---|---|---|
| Q1 | `segno` dependency, `qr_service`, logo centre, tests, PDF of one label (single 50x25 and 60x40) | 2 days |
| Q2 | Label dialog in Stock, multi-select, copies, preview, thermal roll sizes, hang tag | 2-3 days |
| Q3 | Sticker sheets and A4 grid, "start at position N" | 1.5-2 days |
| Q4 | 3D QR variant and 3D card (needs backend item 2) | 1-2 days desktop (+ backend) |
| Q5 | Scanner at the counter: a field on the bill screen that accepts a scanned code and adds the item | 0.5-1 day |

### 1.8 Open questions for you

1. **What is the web address** the codes should open (the shop domain)? Without a real public page the customer scan is pointless.
2. Which **printers** will you use (a thermal label printer? which model and label size?) and which **sticker sheet** brand/size? This decides which formats to build first.
3. Should customers be able to see the **price** by scanning, or only the product story?
4. For 3D: public to anyone, or only by the QR (unlisted link)?
5. Should the full tree + STUDIO logo also appear on the hang tag header (yes by default), with only the small VS mark in the QR centre?

---

## 2. Proper billing system

### 2.1 What exists today (from the code)

- **Counter bill** (`ui/sales_screen.py`): cart with item, price, qty, GST %, CGST/SGST split shown, buyer name and phone required, one shop or a "sold from" place. It sends only `items (item_id, quantity)`, `customer_id`, `client_id`, `location_id` to `POST /sales`. The server prices it (`services/pricing.py` mirrors the rule for display) and numbers it.
- **Invoice number**: the server assigns a consecutive number; the PDF is fetched from `/invoices/<number>/pdf`, saved and opened.
- **History** (`ui/sales_history_screen.py`): list, filters (all / not fully paid / paid / cancelled), view details, reprint, edit payment (owner, manager: status pending/partial/paid and method), delete bill (owner, with a reason: stock returns, bill stays as cancelled).
- **Orders** (`ui/orders_screen.py`, `services/orders_service.py`): payments are proper records (amount, method, reference, date), can be corrected or voided with a reason; a bill is made from an order (`/orders/<id>/invoice`).
- **Offline** (`services/sales_service.queue_offline_sale`): the sale is queued in the outbox with an idempotency id; the server numbers it on sync.
- `bill_text()` already reads `discount` and `tax_total` from the sale, so **the server already has a discount field**; the desktop just never sets it.

### 2.2 Gaps for a proper system

| # | Gap | Today | Needs backend? |
|---|---|---|---|
| 1 | **Discounts** | None at the counter. The sale has a `discount` field the desktop can't fill. | Likely accept `discount` (per bill and per line, amount or %) on `POST /sales`; permission e.g. `sales:sale:discount` with a limit for staff |
| 2 | **Payment taken at billing** | The bill is created "pending", then someone edits the payment later. Part payment has no amount. | Yes: payment lines on `POST /sales` |
| 3 | **Split payments** (part cash, part UPI, card) | Orders can have several payments; counter sales have one method and a status word. | Yes: reuse the order-payment model for sales |
| 4 | **Returns and credit notes** | Only "delete bill" (owner). No partial return, no exchange, no refund record, no credit note number. | Yes: `/sales/<id>/returns`, credit note numbering and PDF, stock back in |
| 5 | **GST invoice correctness** | CGST/SGST always shown, half and half. No IGST for out-of-state buyers, no place of supply, no HSN code per item, no buyer GSTIN on the bill (customers have a `gstin` field). Shop GSTIN lives in the letters profile. | Yes: HSN on item, state on customer, IGST logic, invoice template |
| 6 | **Invoice numbering** | Server numbers consecutively (good), but a financial-year series, a prefix and a no-gaps rule are not visible from the desktop. Cancelled bills keep their number (good, correct for GST). | Check/confirm; FY reset and a separate series for credit notes |
| 7 | **Offline bills** | Queued with a short local reference; **no invoice number and no PDF until synced**, payment hard-coded to "cash", no discount. A customer can leave without a proper bill. | Partly: reserve a block of numbers per device, or print a "provisional receipt" and convert later |
| 8 | **Print formats** | One PDF (server-made), opened in the PDF viewer. No A4 vs A5 vs 80 mm thermal receipt, no direct print, no WhatsApp/email send. | Yes if the server renders; or render the receipt locally (see 2.4) |
| 9 | **Bill edits after the fact** | Only payment status/method. Wrong price or item means delete (owner) and re-bill. | Decide policy (GST allows credit note + new invoice, not silent edits) |
| 10 | **Customer dues** | "Not fully paid" filter exists, no ageing, no statement, no reminders. | Yes (a due-by-customer report) |
| 11 | **Reports** | `/reports/gst-summary` and `/reports/export/sales` exist on the backend with no desktop screen (23 Nov review). | No, desktop only |
| 12 | **Quotation → order → bill** | Letters (quotations) and orders exist separately; no one-click conversion. | Maybe |
| 13 | **Roles** | `sales:sale:create/read/edit`, `sales:invoice:read`, `sales:order:*` exist. No action for discount, return, or cancel-with-limit. | Yes: new actions (see 2.5) |

### 2.3 Proposed steps

| Phase | Work | Backend | Effort |
|---|---|---|---|
| B1 | **Payment at the till**: pay-now box on the bill screen (cash / UPI / card, amount received, change, balance), part payment amount, "mark paid" default. Sale history shows amounts paid and balance. | Payment lines on `POST /sales` | 3-4 days |
| B2 | **Discounts**: per-line and bill discount (amount or %), reason, limit per role, shown on the bill and in `bill_text`. | `discount` input, role limit, audit | 2-3 days |
| B3 | **Split payments**: several payment rows on one bill, same dialogs as orders. | Reuse order payment model | 2 days |
| B4 | **Returns and credit notes**: "Return items" from history (pick lines and quantities, reason, refund method), credit-note number and PDF, stock back in, shown in history and the GST summary. | New endpoints | 4-5 days |
| B5 | **GST correctness**: HSN on items, state on customers, IGST, buyer GSTIN, GST summary screen (use `/reports/gst-summary`). | HSN, state, template | 3-4 days |
| B6 | **Print formats and offline**: local receipt renderer (A4, A5, 80 mm thermal) with QR to the bill, "provisional receipt" when offline and conversion on sync, direct print. Shares the printing helper built in phase Q1. | Number-block reservation or provisional-number scheme | 3-4 days |
| B7 | **Dues and statements**: customer ledger, ageing, send reminder (WhatsApp/email link). | Dues endpoint | 2 days |

### 2.4 One design decision to make early

**Who draws the bill?** Today the server does. Keeping it that way keeps one source of truth for GST wording, but it cannot print offline and has only one layout. Drawing the receipt on the desktop (we will have `QPdfWriter` and label code from phase Q1) allows thermal 80 mm receipts and offline bills, but the official tax invoice must still match the server's numbers. Recommendation: **server stays the legal invoice (A4 GST invoice)**; the desktop adds a **thermal/short receipt** and a **provisional receipt** when offline, both clearly marked as such.

### 2.5 Roles (using `Session.can`)

New actions to ask the backend for (names are proposals; align with its IAM naming): `sales:sale:discount` (with a % limit), `sales:sale:return`, `sales:sale:cancel`, `sales:credit_note:read`, `sales:payment:refund`. Screens hide buttons with `Session.can(...)` as the rest of the code does. The built-in roles in `services/builtin_roles.py` would get sensible defaults (owner all; manager discount up to a limit and returns; cashier create only).

### 2.6 Open questions for you

1. Are you **GST-registered** and do you ever sell **out of state** (IGST)? Do your items have HSN codes? (Furniture and wood carvings have specific HSN codes; ask your accountant.)
2. **Discount rules:** who may give a discount and how much without the owner?
3. **Returns policy:** do you take returns/exchanges? Refund as cash, or store credit only?
4. Should the customer be able to **pay by UPI QR on the bill screen** (a UPI QR with the amount)? It is a different QR from the product QR; cheap to add, but you need a UPI id.
5. **Offline:** how often is the shop actually offline? If rarely, a provisional receipt is enough; if often, number blocks per device are worth building.
6. Receipt printer: thermal 80 mm, A4 laser, or both?

---

## 3. Proper HR management

### 3.1 What exists today

- **Staff** (`ui/staff_screen.py`, `services/staff_service.py`): list, add (invite email sets a password), edit name, email, phone, role, daily wage, switch on/off, extra roles per place (`ExtraRolesDialog`, PR #48), change own password.
- **Attendance** (`ui/attendance_screen.py`, `services/workforce_service.py`): check in / check out, an on-site / off-site tag, admin sees everyone (`attendance:record:read_all`), own record otherwise. The service is thin: check-in, check-out, own list, all list with dates and user filter.
- **Payroll** (`ui/payroll_screen.py`): daily wages from attendance + piece work, overtime, bonus (`WorkEntryDialog`) + advance given / taken back (`AdvanceDialog`) + "Pay everything up to a date" (`PayDialog`, optionally taking back part of the advance). Paying is what counts wages in profit.
- Permissions now: `attendance:record:*`, `payroll:*` (summary, entry, advance, payment, records), `people:user:read`, `people:user:read_pay`.

### 3.2 Gaps

| # | Gap | Today | Backend? |
|---|---|---|---|
| 1 | **Leave** | Nothing. No leave types, balance, request or approval. Absence just means no attendance. | Yes: leave types, balances, requests, approval |
| 2 | **Shifts and holidays** | No shift times, no late/early marking, no weekly off, no holiday calendar. Overtime is typed by hand in payroll. | Yes: shifts, holidays, rules |
| 3 | **Attendance corrections** | `attendance:record:edit` exists as a permission; the screen has no "fix this day" or regularisation request, no half-day, no monthly sheet view. | Partly (endpoint exists per the permission; confirm) |
| 4 | **Salary history** | `base_daily_wage` is one field, overwritten when edited. No "from date", no record of who changed it. Pay for past days can change silently. | Yes: wage history with effective dates |
| 5 | **Payslips** | Payment records exist, but no printable payslip (earned, extras, advance taken back, net, signature). | Light: desktop can render from existing payroll data; a server record is better for reprints |
| 6 | **Own pay view** | Review of 23 Nov: there is no "read own pay" action; staff cannot see their own pay history. | Yes: new action, e.g. `payroll:records:read_own` |
| 7 | **Employee profile and documents** | Name, email, phone only. No joining date, address, emergency contact, ID proof, bank/UPI for payment, photo, contract, skill. | Yes: profile fields and a document store (the assets store may do) |
| 8 | **Deductions and statutory** | Only advance recovery. No fines, PF/ESI/TDS (probably not needed for a small workshop, but ask). | Optional |
| 9 | **Piece-rate rate card** | Piece work rate typed each time. No standard rates per carving type; production jobs (backend only) do not feed payroll. | Yes (link production jobs to pay) |
| 10 | **Reports** | No monthly attendance report, no cost per worker, no leave report, no export. | Partly |
| 11 | **Onboarding / offboarding** | Switch off an account. No last working day, final settlement, return of advance balance. | Light |
| 12 | **Team structure** | Backend has `/team/tree` and `/team/attendance` with no screen. | No, desktop only |
| 13 | **Roles** | Attendance and payroll are already gated with `Session.can`; leave, shift, documents and salary history need new actions. | Yes |

### 3.3 Proposed steps

| Phase | Work | Backend | Effort |
|---|---|---|---|
| H1 | **Payslip PDF** from existing payroll data (desktop `QPdfWriter`, reuse printing helper from Q1) and a **"My pay"** view for each worker. | `read_own` action (the PDF itself needs nothing) | 2-3 days |
| H2 | **Salary history**: wage with effective-from date, history table in the staff dialog, payroll uses the wage that applied on each day. | Wage history + payroll change | 2-3 days |
| H3 | **Attendance sheet**: month grid per person (present, half, absent, leave, holiday), fix a day with a reason (`attendance:record:edit`), team view (`/team/attendance`). | Confirm edit endpoint | 3-4 days |
| H4 | **Leave**: types (casual, sick, unpaid), balance, request from staff, approve/reject by manager, shows in the attendance sheet and in payroll (unpaid leave). | Full leave module | 4-5 days desktop (+ backend) |
| H5 | **Shifts and holidays**: shift per person, holiday calendar, late/early marks, overtime suggested from the shift. | Shifts and holidays | 3-4 days |
| H6 | **Profile and documents**: joining date, address, emergency contact, ID proof upload, UPI/bank for pay, photo. | Fields + document store | 2-3 days |
| H7 | **Reports and exit**: monthly attendance and pay report to Excel/PDF, last working day and final settlement. | Reports | 2 days |

### 3.4 Roles (using `Session.can`)

Existing actions cover the screens as they are. Proposed new ones: `payroll:records:read_own` (own pay), `leave:request:create`, `leave:request:approve`, `leave:balance:read_all`, `shifts:shift:manage`, `people:user:read_documents`, `people:user:write_documents`, `people:wage:edit_history`. Workers get "request leave" and "read own pay"; managers get approve; only the owner sees other people's pay (`people:user:read_pay`, as now).

### 3.5 Open questions for you

1. **How many people**, and are they all daily-wage, or are some monthly salary? (Monthly salary changes the payroll model; today it is only daily plus extras.)
2. Do you want **leave and shifts at all**, or is a month attendance sheet plus payslips enough? (Recommendation: H1-H3 first, then ask.)
3. Do workers log in themselves (own check-in, own pay view), or does a manager do everything for them?
4. Any **PF / ESI / TDS**? (Usually not for a small workshop; confirm with your accountant.)
5. Paid by cash, UPI or bank? (Decides whether to store payment details.)
6. How sensitive are ID proofs? Aadhaar must be stored carefully; we may choose to store only the last 4 digits, or not store it at all.

---

## 4. Shared pieces and order

- **One printing helper** (page size, painter, PDF or printer, preview) built in Q1 is reused by billing (B6) and HR (H1). Build it once, in `services/printing.py`, so all three do not each reinvent printing.
- **Backend list, in order of use:**
  1. Public product page and public 3D link (Q4).
  2. Payment lines and discount on `POST /sales` (B1-B3).
  3. Credit notes and returns (B4).
  4. HSN, state, IGST, invoice template (B5).
  5. Own-pay action, wage history (H1-H2).
  6. Leave, shifts, holidays, profile/documents (H4-H6).
  Open one ticket per group in `nakamadesk-backend` and point it at this file.
- **Not in scope here:** the three open items from the 23 Nov backend review (extra-role read endpoint, offline `/iam/me` cache, stand-in actions). They touch the same permissions code and are worth doing before adding more actions.

### Suggested sequence

| Order | Phases | Why |
|---|---|---|
| 1 | Q1-Q3 | Self-contained; gives printing helper; needs only a shop web address |
| 2 | B1-B3 | Money correctness at the counter |
| 3 | H1-H3 | Payslips and attendance sheet; mostly desktop-only |
| 4 | B4-B5 | Returns and GST need accounting decisions and backend work |
| 5 | Q4-Q5, B6-B7, H4-H7 | Depend on backend or on your answers above |

Total if everything is built: roughly 35-50 developer-days across both repos.
