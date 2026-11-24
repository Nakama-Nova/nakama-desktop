"""
services/builtin_roles.py

What the 7 built-in roles may do, as backend actions. Used only when the server is
too old to answer GET /iam/me (or cannot be reached right after a restart), so the
app behaves as it did when roles were a fixed list. A copy of the built-in roles in
the backend's app/iam/defaults.py: when a module moves over there, add it here too.
"""

# fmt: off
_PAYMASTER = (
    "payroll:summary:read", "payroll:entry:write", "payroll:advance:write",
    "payroll:payment:create", "payroll:records:read_all",
)
_ATTENDANCE_DESK = ("attendance:record:write", "attendance:record:read_all")
_ATTENDANCE_BOSS = _ATTENDANCE_DESK + ("attendance:record:edit", "attendance:presence:mark")
_SALES_DESK = (
    "sales:sale:create", "sales:sale:read", "sales:order:create", "sales:order:read",
    "sales:order:payment_add", "sales:order:invoice", "sales:invoice:read",
    "sales:customer:read", "sales:customer:write", "purchases:purchase:read",
    "sales:payment:add", "sales:credit_note:read",
)
_SALES_BOSS = _SALES_DESK + (
    "sales:sale:edit", "sales:order:update", "sales:order:delete", "sales:customer:delete",
    "purchases:purchase:create", "purchases:purchase:confirm",
    "sales:payment:void", "sales:sale:return",
)
_FLOOR_VIEW = ("items:item:read", "attendance:record:read_own")
_PRODUCTION_BOSS = (
    "production:job:create", "production:job:read", "production:job:assign", "production:job:run",
    "bom:entry:read", "items:item:read", "attendance:record:read_own", "items:cost:read",
    "items:item:write", "items:stock:adjust", "inventory:raw_material:read",
    "inventory:raw_material:write", "inventory:raw_material:adjust",
    "inventory:stock_location:view", "inventory:stock_location:transfer",
    "inventory:master:read", "inventory:master:write", "machines:machine:read",
    "machines:machine:write", "machines:tool:view", "machines:tool:manage",
)
_ACHARI = (
    "production:job:read", "bom:entry:read", "bom:entry:write", "lab:part:read",
    "items:item:read", "attendance:record:read_own", "machines:tool:view",
)
_LAB_BOSS = (
    "lab:part:read", "lab:part:edit", "scans:job:work", "scans:job:process",
    "expenses:expense:write", "assets:file:read", "assets:file:read_all", "assets:file:write",
)
_ARTISAN = ("lab:part:read", "restoration:project:access", "scans:job:work", "assets:file:read")
_DOCS_DESK = ("letters:quotation:issue", "letters:order_confirmation:issue")
_DOCS_BOSS = _DOCS_DESK + (
    "letters:purchase_receipt:issue", "budgets:budget:read", "reports:report:read",
    "reports:dashboard:read",
)
_PEOPLE_DESK = ("people:user:read",)
_PEOPLE_BOSS = _PEOPLE_DESK + (
    "people:user:read_pay", "comments:comment:review", "site:content:manage", "site:stats:read",
)

BUILTIN_ACTIONS: dict[str, tuple[str, ...]] = {
    "owner": ("*",),
    "manager": (
        ("finance:ledger:read", "iam:role:read", "iam:role:write", "iam:user_role:assign")
        + _PAYMASTER + _ATTENDANCE_BOSS + _SALES_BOSS + _PRODUCTION_BOSS
        + _LAB_BOSS + _DOCS_BOSS + _PEOPLE_BOSS + ("leave:request:create", "leave:request:approve", "leave:request:read_all")
    ),
    "accountant": ("finance:ledger:read", "finance:balance_sheet:read"),
    "sales": (
        _ATTENDANCE_DESK + _SALES_DESK + _FLOOR_VIEW
        + ("inventory:stock_location:view",) + _DOCS_DESK + _PEOPLE_DESK
    ),
    "achari": _ACHARI,
    "worker": _FLOOR_VIEW + ("lab:part:read",),
    "artisan": _FLOOR_VIEW + _ARTISAN,
}
# fmt: on
