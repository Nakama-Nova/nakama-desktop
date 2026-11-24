"""
services/billing.py

The till's arithmetic: the bill total with a discount, and what the customer handed over.
Same rules as the server (app/services/sales_service.py there): the discount is a rupee
amount taken off the bill total (items + GST), never more than the bill.
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
METHODS = [("Cash", "cash"), ("UPI", "upi"), ("Card", "card"), ("Bank transfer", "bank"), ("Cheque", "cheque")]


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def discount_amount(gross, kind: str, value) -> float:
    """The rupees off a bill of `gross`. kind is "amount" or "percent". Capped at the bill."""
    gross, value = _d(gross), max(_d(value), Decimal(0))
    off = gross * min(value, Decimal(100)) / 100 if kind == "percent" else value
    return float(_cents(min(off, gross)))


def payment_status(total, received) -> str:
    """paid when the customer covered the bill, part when something was handed over, else pending."""
    total, received = _cents(_d(total)), _cents(_d(received))
    if total <= 0 or received >= total:
        return "paid"
    return "partial" if received > 0 else "pending"


def change_or_balance(total, received) -> tuple[str, float]:
    """("change", rupees to hand back) or ("balance", rupees still to pay)."""
    diff = _cents(_d(received)) - _cents(_d(total))
    return ("change", float(diff)) if diff >= 0 else ("balance", float(-diff))


def received_total(*amounts) -> float:
    """What the customer handed over across all the payment rows."""
    return float(sum((_cents(_d(a)) for a in amounts), Decimal(0)))


def refund_estimate(lines: list[tuple], bill_discount) -> float:
    """What a return will refund, as the server works it out: each line's share of its total
    (items + GST), after its share of the bill discount (spread over the lines in proportion to
    their totals). lines: [(line_total, sold_quantity, return_quantity)] for ALL lines of the bill."""
    gross = sum((_d(t) for t, _s, _q in lines), Decimal(0))
    keep = 1 - (min(_d(bill_discount), gross) / gross) if gross else Decimal(1)
    return float(sum((_cents(_d(t) * q / s * keep) for t, s, q in lines if s and q), Decimal(0)))
