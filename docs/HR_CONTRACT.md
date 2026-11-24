# HR (phases H2, H4, H5, H6): API contract

The agreement between the backend (`nakamadesk-backend`) and the desktop for the HR upgrade. Both sides build to this file; if the backend must change something it says so in its PR description (the desktop session owns this file).

Starting point on backend `main`: users with `base_daily_wage`, `/attendance/*` (check in/out, `status` present / absent / half-day, `total_hours`, `daily_wage`), `/payroll/summary`, `/payroll/me`, `/payroll/payments`, work entries and advances, IAM roles/actions. No leave, shifts, holidays, wage history, profile/documents, pay types other than a daily wage.

Money `Decimal`, rupees. Dates ISO. Ids UUID.

---

## H2. Pay type and salary history

### User fields (added to the user and its responses)
`pay_type`: `daily` (default, today's behaviour) | `weekly` | `monthly` | `hourly`.
`employment`: `full_time` (default) | `part_time` (a label for reports; pay follows `pay_type`).
`pay_amount`: the rate for the pay type (per day, per week, per month, or per hour). `base_daily_wage` stays and always equals the daily rate in force (for `weekly` = amount / 7, `monthly` = amount / days in the current month, `hourly` = amount x 8), so older screens keep working.

### Wage history (table `user_wages`)
`id`, `user_id`, `pay_type`, `amount`, `effective_from` (date), `note`, `created_by`, `created_at`.
- `GET /people/users/{id}/wages` newest first.
- `POST /people/users/{id}/wages` `{pay_type, amount, effective_from, note?}` adds a row and updates the user's `pay_type` / `pay_amount` when `effective_from` is today or earlier. Not backdated more than the last pay-out date (409 "Wages up to <date> are already paid").
- Editing a user's `base_daily_wage` / `pay_type` / `pay_amount` through the old route also writes a history row (`effective_from` = today) so nothing changes silently.
- **Payroll uses the rate in force on each day.** Pay for a past day does not move when the rate changes.

### Pay for each type (what `/payroll/summary` and `/payroll/me` report as `pending_daily`)
- `daily`: wage x present days (half-day = half), as today.
- `hourly`: `amount` x `total_hours` of the days worked.
- `weekly` and `monthly`: `amount` / 7 (or / days in the month) for **every payable day**: present, half-day (half), approved paid leave, public paid holidays and weekly offs that fall in the period; nothing for absent days and unpaid leave. Paid up to a date like the others.
- The summary row gains `pay_type`, `employment`, `payable_days`, `unpaid_days`.

### Permissions
`people:wage:history_read` (owner, manager), `people:wage:history_write` (owner).

---

## H4. Leave

### Tables
`leave_types`: `id`, `name`, `paid` (bool), `yearly_days` (nullable = no limit), `active`. Seeded: Casual leave (paid, 12), Sick leave (paid, 6), Unpaid leave (unpaid, no limit).
`leave_requests`: `id`, `user_id`, `leave_type_id`, `from_date`, `to_date`, `half_day` (bool, only when one day), `days` (computed, skips weekly offs and holidays), `reason`, `status` (`pending|approved|rejected|cancelled`), `decided_by`, `decided_at`, `decision_note`, `created_at`.

### Routes
| Route | Notes |
|---|---|
| `GET /leave/types` | everyone |
| `POST /leave/requests` `{leave_type_id, from_date, to_date, half_day?, reason?}` | for yourself; 422 when it overlaps another pending/approved request, or exceeds the balance of a limited type ("Only N days of Casual leave left") |
| `GET /leave/requests?status=&user_id=&from=&to=` | you see yours; with `leave:request:read_all` everyone's |
| `POST /leave/requests/{id}/approve` `{note?}` / `/reject` `{note}` | approver cannot decide their own request; approval writes the days into attendance as `leave` (see below) |
| `POST /leave/requests/{id}/cancel` | the requester, while pending (or before it starts when approved: the days are freed) |
| `GET /leave/balances/me` and `GET /leave/balances?user_id=` | `[{leave_type_id, name, yearly_days, used, pending, left}]` for the leave year (April to March) |

### Attendance
`status` gains `leave` (`present, absent, half-day, leave`). A leave day carries `leave_type_id` and `paid`. `GET /attendance/all` and `/attendance/my` include approved leave days and holidays (as rows with `status` `leave` or `holiday`, no check-in) so the desktop sheet needs no second call.

### Permissions
`leave:request:create` (everyone with an account), `leave:request:read_all` and `leave:request:approve` (owner, manager), `leave:balance:read_all` (owner, manager), `leave:type:manage` (owner).

---

## H5. Shifts and holidays

`shifts`: `id`, `name`, `start_time`, `end_time`, `grace_minutes` (default 10), `weekly_off` (list of weekday numbers, 0 = Monday), `active`. A user has an optional `shift_id`.
`holidays`: `id`, `date`, `name`, `paid` (bool, default true).

| Route | Notes |
|---|---|
| `GET /shifts`, `POST /shifts`, `PUT /shifts/{id}`, `DELETE /shifts/{id}` (409 if in use) | manage: `shifts:shift:manage` (owner, manager); read: everyone |
| `PUT /people/users/{id}/shift` `{shift_id|null}` | `shifts:shift:manage` |
| `GET /holidays?year=`, `POST /holidays`, `DELETE /holidays/{id}` | manage: `holidays:holiday:manage` (owner, manager) |

Attendance response gains `late_minutes` (check-in after shift start + grace) and `early_leave_minutes`; both 0 without a shift. Overtime suggestion: `GET /payroll/summary` row gains `overtime_hours_suggested` (hours past shift end), never paid automatically.

---

## H6. Profile and documents

### User fields
`joining_date`, `last_working_date` (nullable), `address`, `emergency_contact_name`, `emergency_contact_phone`, `pay_upi` (UPI id, or null), `id_proof_type` (`aadhaar|pan|voter|driving|other`), `id_proof_last4` (only the last four characters, **never the full number**; the backend rejects anything longer than 4 characters).

### Documents (ID proof scans, contract, photo)
`user_documents`: `id`, `user_id`, `kind` (`id_proof|contract|photo|other`), `filename`, `content_type`, `size`, `uploaded_by`, `uploaded_at`.
Same upload pattern as product photos (the desktop already does "upload straight to the storage bucket"): `POST /people/users/{id}/documents/upload-url` `{kind, filename, content_type, size}` -> `{document_id, upload_url, headers}`; the desktop PUTs the file; `POST /people/users/{id}/documents/{document_id}/confirm`. `GET /people/users/{id}/documents` returns rows with a short-lived signed `url`. `DELETE` is owner-only. Max 10 MB, images and PDF only. Private storage, never public.

### Exit
`POST /people/users/{id}/offboard` `{last_working_date, note?}`: sets `last_working_date`, switches the account off from the day after, and returns the final settlement (`pending_daily`, `pending_extras`, `advance_balance`, `net_to_pay`). The owner then pays it with the normal pay-out.

### Permissions
`people:user:read_documents` and `people:user:write_documents` (owner; manager read), `people:user:offboard` (owner). Profile fields are read with `people:user:read`; `pay_upi`, wage and ID fields only with `people:user:read_pay`.

---

## Desktop (this repo) uses
- Staff form: pay type, amount, part/full time, joining date, address, emergency contact, UPI, ID proof last 4, shift; a wage history table; a documents list; "Offboard".
- A Leave screen (request, my balances, approve/reject), a Holidays and shifts section, an attendance month sheet (reads the leave and holiday rows), a payslip from any pay-out.
- When the server does not send a new field the screens hide that part, so the desktop still runs against an older server.
