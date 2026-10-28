"""
services/pricing.py

The same pricing rule the server uses (app/services/pricing.py there), so a form can
show a price before it is saved and a screen can show a price from a cached item:

    cost           = buying price + making cost
    selling price  = cost + profit %           (stored on the product, before GST)
    price with GST = selling price + GST %     (what the customer pays)
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def cost_of(purchase_price, production_cost) -> float:
    return float(_round(_d(purchase_price) + _d(production_cost)))


def price_from_cost(cost, profit_percent) -> float:
    """Selling price before GST."""
    return float(_round(_d(cost) * (1 + _d(profit_percent) / 100)))


def with_gst(net_price, gst_percent) -> float:
    """What the customer pays for a price that does not include GST yet."""
    return float(_round(_d(net_price) * (1 + _d(gst_percent) / 100)))


def net_from_gross(gross_price, gst_percent) -> float:
    """The price before GST, from one that includes it."""
    return float(_round(_d(gross_price) / (1 + _d(gst_percent) / 100)))


def profit_percent_of(cost, net_price) -> float | None:
    """The margin a price leaves over cost, or None when there is no cost to compare."""
    if _d(cost) <= 0:
        return None
    return float(_round((_d(net_price) / _d(cost) - 1) * 100))


def price_with_gst(item: dict) -> float:
    """A product dict's customer price: the server's figure, or worked out for a cached one."""
    if item.get("price_with_gst") is not None:
        return float(item["price_with_gst"])
    return with_gst(item.get("selling_price"), item.get("gst_percent"))
