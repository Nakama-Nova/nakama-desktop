"""
services/money.py

Rupee amounts the way an Indian shop writes them: the last three digits, then pairs
(₹1,84,600.00, not ₹184,600.00).
"""

from decimal import ROUND_HALF_UP, Decimal


def inr(value, places: int = 2) -> str:
    """₹ with lakh grouping. None or blank counts as 0."""
    amount = Decimal(str(value or 0)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    whole, _, frac = f"{abs(amount):f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if places else "")
