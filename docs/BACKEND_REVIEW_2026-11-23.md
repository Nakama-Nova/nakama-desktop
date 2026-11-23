# Desktop vs backend review, 23 Nov 2026

Compared this repo (`main` at fb6bf70, plus open PR #48) with `nakamadesk-backend` `main` at e20a5d4 (includes the merged IAM work, backend PR #124).
The local `nakamadesk-backend` folder is on `feature/order-invoice` from 30 Oct, so it is out of date. Pull `main` before checking anything against it.

## 1. Do the desktop's calls match the backend?

Yes for every call I could check by reading the code. 137 call sites (method and path) were matched against the backend's route table. Nothing points at a route that does not exist.
Not checked: calls built from a variable (`/{kind}/...` in `stock_service.py`, `/letters/{kind}`), request and response field names, and anything run against a live server.

PR #48 uses `GET /iam/me`, `GET /iam/roles`, `PUT /iam/users/{id}/roles`, and the policy and role endpoints. All exist on backend `main`.

## 2. Things to fix or decide in PR #48 (permissions)

1. **"Extra roles" can wipe a person's roles by accident.** `PUT /iam/users/{id}/roles` replaces all extra roles, and there is no endpoint that lists them, so the dialog opens empty. Saving it with nothing ticked removes whatever the person had.
   It also ends that person's sessions (the backend raises `token_version`), so they are signed out.
   Suggestion: ask the backend for a read (`GET /iam/users/{id}/roles`, or an `extra_roles` field on the user). Until then, warn in the dialog: "This replaces the person's extra roles and signs them out."
2. **Offline restart with a custom role leaves the user with no access.** Already noted in the PR. Caching the last `/iam/me` answer in the keyring next to the token would fix it.
3. **Menu rules the backend cannot answer yet** (from the PR notes): no "read own pay" action, Purchases and Designs use stand-in actions. Worth one backend ticket so the desktop does not guess.
4. Not tried against a live PR-124 server. Do that before merging.

## 3. Backend features with no desktop screen

| Backend route | What it would give the shop |
|---|---|
| `/production/jobs` (create, assign worker, start, complete) | Workshop job board. Workshop section has Lab, Restoration, Designs, Machines only |
| `/reports/gst-summary`, `/reports/top-products`, `/reports/export/sales` | GST return figures, best sellers, a sales export |
| `/finance/journal`, `PUT /finance/entries/{id}`, `/finance/entries/{id}/reverse`, `/finance/accounts` (create) | Desktop Accounts is read-only; fixes need another tool |
| `/machines/due`, `/budgets/warnings` | Overdue maintenance and over-budget warnings on Home |
| `PUT /orders/{id}/items` | Edit an order's items after it is created |
| `/team/tree`, `/team/attendance` | Who reports to whom, team attendance |
| `/bom/...` | Parts list for a product |

Order of value for a furniture shop: GST summary and production jobs first, then the Home warnings (small, and they use data already on the server).

## 4. Design suggestions

Brand direction is already good: warm cream surface, brown and gold, Cormorant Garamond headings over Inter, an empty state with a real product photo. Suggestions are about consistency and robustness.

1. **Icons render as empty boxes in the committed screenshots** (`docs/screenshots/bootstrap-ui/*.png`: sidebar, buttons, the greeting). The icons are emoji characters (`ui/main_window.py` header says so). Check on a real Windows 10 PC; if they show correctly there, regenerate the screenshots so the docs match. Either way, bundled SVG icons (recoloured by theme) would look the same on every PC and match the brand better than emoji.
2. **Quick Actions on Home use three unrelated button colours** (green, brown, gold) for equal-weight actions. Use one primary (New Bill), the others outlined. Colour then means "main action", and green stays for "paid / success".
3. **Table header columns centre some titles and left-align others** (Orders: "Items" is centred over left-aligned text). Align headers the same way as their cells; money columns right-aligned.
4. **Stylesheets are written inline in every screen** (`setStyleSheet` appears 20-31 times in each of `orders_screen`, `restoration_screen`, `payroll_screen`, `sales_screen`, ...). `Theme.btn()`, `Theme.card()` and `Theme.badge()` exist; moving the screens onto them makes the dark theme in the blueprint a one-file change instead of a rewrite.
5. **Sidebar** has 20+ entries at 1366x728 and needs a scrollbar to reach Money. Collapse sections (Selling, Stock, Workshop, People, Money) and remember which are open.
6. **Error text:** PR #48 now shows the server's 403 reason. Keep that pattern everywhere: say what was refused and who can do it ("Only an owner can change roles"), rather than a generic "Something went wrong".

## 5. Who to tell

- `Chaithumoorpa` owns PR #48 and the backend IAM work: sections 2 and 3.
- `Muthurajut` is a collaborator on the desktop repo with no recent commits: sections 1 and 4 for awareness.
