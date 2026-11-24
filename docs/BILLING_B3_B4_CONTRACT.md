# Billing B3 (split payments) and B4 (returns, credit notes): API contract

The agreement between the backend (`nakamadesk-backend`) and the desktop for the two features. Both sides build to this. If the backend needs to change something, change this file in the same PR so the desktop sees it.

Base: backend `main` today has `POST /sales` (already takes `discount`, `payment_method`, `payment_status`), `GET /sales`, `GET /sales/{id}`, `GET /sales/{id}/items`, `PATCH /sales/{id}` (payment status/method), `DELETE /sales/{id}` (cancel, with reason), `GET /invoices/{number}/pdf`, and for **orders** a payments model (`app/models/order_payment.py`, add / correct / void). Sales have no payment rows and no returns.

Money: `Decimal`, two places, rupees. Dates ISO 8601. Ids UUID strings.

---

## B3. Payments on a bill

### Table `sale_payments` (mirror `order_payments`)
`id`, `sale_id` (FK), `amount` (> 0), `method` (`cash|upi|card|bank|cheque`), `reference` (nullable: UPI/cheque number), `note` (nullable), `paid_on` (date, default today), `created_by`, `created_at`, `voided_at` (nullable), `void_reason` (nullable), `voided_by` (nullable).

### Changes to `SaleResponse`
Add: `amount_paid` (sum of un-voided payments), `balance_due` (`total_amount - amount_paid`, never below 0), `payments: [PaymentResponse]` (all rows, voided ones included, flagged by `voided_at`).
`payment_status` is **derived** after every change: `paid` when `amount_paid >= total_amount`, `partial` when `0 < amount_paid < total_amount`, `pending` otherwise. `payment_method` is the method of the single un-voided payment, or `"split"` when there are several methods, or null when none.

### `POST /sales` (changed, backward compatible)
New optional field `payments: [{amount, method, reference?, note?}]`.
- Given: create one payment row each; the sum must not exceed the bill total (422 "More than the bill" otherwise); status and method derived as above.
- Not given (the old way): `payment_status == "paid"` with a `payment_method` creates one payment of the full total; `partial` or `pending` creates no row (amount unknown). `payment_method` alone with `pending` is ignored.
- Idempotent replay with the same `client_id` returns the existing sale and creates nothing.

### New routes
| Route | Body | Result | Notes |
|---|---|---|---|
| `POST /sales/{id}/payments` | `{amount, method, reference?, note?, paid_on?}` | `SaleResponse` | 409 if the bill is cancelled; 422 if `amount` > `balance_due` ("The bill has only ₹X left to pay") |
| `POST /sales/{id}/payments/{payment_id}/void` | `{reason}` (required, non-empty) | `SaleResponse` | Row stays with `voided_at`/`void_reason`; status re-derived; 409 if already voided |

`PATCH /sales/{id}` stays for correcting method/status on old bills that have no payment rows; for a bill with payment rows it returns 409 "Use the payments".

### Permissions (new IAM actions, added to the built-in roles via a migration like `e5f6a7b8c9d0_grant_sales_and_purchases_actions.py`)
`sales:payment:add` (owner, manager, and whoever has `sales:sale:create`), `sales:payment:void` (owner, manager).

### Offline sync
`SalePayload` accepts `payments` (same shape, optional) and `discount`, `payment_status`; `apply_create` passes them to `build_sale`. Until this ships the desktop keeps refusing discounts offline.

---

## B4. Returns and credit notes

### Tables
`sale_returns` = one credit note: `id`, `credit_note_number` (own series, e.g. `CN/26-27/0001`, from `invoice_counters` with a new counter key and the same financial-year reset rule as invoices; never reused, never has gaps), `sale_id`, `reason` (required), `refund_method` (`cash|upi|card|bank|cheque|store_credit`), `refund_amount`, `restocked` (bool), `created_by`, `created_at`.
`sale_return_items`: `id`, `return_id`, `sale_item_id`, `item_id`, `quantity` (> 0), `taxable_value`, `cgst_amount`, `sgst_amount`, `amount` (what the customer gets back for these units).

### Rules
- A line can be returned up to `sold quantity - already returned` (422 "Only N left to return of <item>").
- Refund per line = `quantity / sold_quantity x line total_price`, after taking the line's share of the bill discount (the discount is spread over the lines in proportion to their `total_price`). GST (CGST/SGST) is returned in the same proportion. Round per line to the paisa; `refund_amount` is the sum of the rounded lines.
- `restock` (request flag, default true): when true, stock for each returned line goes back to the sale's `location_id` through the normal stock-movement path (reason "Sales return <credit note number>"). When false (damaged goods) stock is not changed.
- The bill itself is not edited and keeps its number. A cancelled bill cannot be returned (409).
- The refund counts in the books the same way a cancelled bill does: reduces revenue and GST of the month the credit note is dated (`/reports/gst-summary` and the sales report subtract credit notes).

### Routes
| Route | Body | Result |
|---|---|---|
| `POST /sales/{id}/returns` | `{items: [{sale_item_id, quantity}], reason, refund_method, restock?: true}` | `ReturnResponse` |
| `GET /sales/{id}/returns` | | `[ReturnResponse]` newest first |
| `GET /returns/{credit_note_number}/pdf` | | the credit note PDF (shop name and GSTIN from the letters profile, the original invoice number and date, each returned line with GST, total refunded, the reason and the refund method) |

`ReturnResponse`: `id`, `credit_note_number`, `sale_id`, `invoice_number`, `reason`, `refund_method`, `refund_amount`, `restocked`, `created_at`, `items: [{sale_item_id, item_name, quantity, taxable_value, cgst_amount, sgst_amount, amount}]`.

### Changes to `SaleResponse`
Add `returned_total` (sum of `refund_amount`s) and `returned_quantities: {sale_item_id: quantity}` so the screen can show what is left to return without a second call.

### Permissions
`sales:sale:return` (owner, manager). `sales:credit_note:read` (anyone with `sales:invoice:read`).

---

## Desktop (this repo) uses
- `SalesService.add_payment / void_payment / returns / create_return / credit_note_pdf` in `services/sales_service.py`.
- Till: several payment rows on one bill (method + amount each).
- Bill History: a Payments window (list, add, void) and a Return items window; credit-note PDF opens like a bill PDF.
- Screens read `amount_paid`, `balance_due`, `payments`, `returned_total`, `returned_quantities` when present and fall back to today's behaviour when the server does not send them (so the desktop still runs against an older server).
