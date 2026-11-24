"""
services/dues.py

Who owes the shop money: the unpaid bills of each buyer, how long the oldest has been open,
and the words of a polite reminder.
"""

from datetime import date, datetime
from urllib.parse import quote


def _day(sale: dict) -> date | None:
    text = str(sale.get("invoice_date") or sale.get("created_at") or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def due_of(sale: dict) -> float:
    """What is still to pay on a bill. A server that tracks payments says it (balance_due); an
    older one only says paid / part paid / not paid, so a part-paid bill counts in full."""
    if (sale.get("order_status") or "") == "cancelled" or sale.get("payment_status") == "paid":
        return 0.0
    if sale.get("balance_due") is not None:
        return float(sale["balance_due"])
    return float(sale.get("total_amount") or 0)


def dues_by_customer(sales: list[dict], today: date | None = None) -> dict:
    """{customer_id: {"owed", "days" (since the oldest unpaid bill), "bills": [sale, ...] oldest first}}."""
    today = today or date.today()
    out: dict = {}
    for s in sales:
        owed = due_of(s)
        cid = s.get("customer_id")
        if owed <= 0 or not cid:
            continue
        row = out.setdefault(str(cid), {"owed": 0.0, "days": 0, "bills": []})
        row["owed"] = round(row["owed"] + owed, 2)
        row["bills"].append(s)
    for row in out.values():
        row["bills"].sort(key=lambda s: str(s.get("created_at") or ""))
        first = _day(row["bills"][0])
        row["days"] = (today - first).days if first else 0
    return out


def reminder_text(name: str, owed_text: str, bills: list[str], shop: str = "Vriksha Studios") -> str:
    listed = ", ".join(bills[:5]) + (" and more" if len(bills) > 5 else "")
    return (
        f"Namaste {name}, this is a gentle reminder from {shop}: {owed_text} is still pending"
        + (f" for bill {listed}" if bills else "")
        + ". Kindly pay when convenient. Thank you."
    )


def whatsapp_link(phone: str, text: str) -> str | None:
    """wa.me link that opens a chat with the message typed in; the person presses send themselves.
    Ten-digit Indian numbers get 91 in front."""
    digits = "".join(ch for ch in phone or "" if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return f"https://wa.me/{digits}?text={quote(text)}" if len(digits) >= 11 else None
