"""
services/gst.py

GSTIN checks and the GST return figures: is a buyer's GSTIN well formed (15 characters with
the check letter), which state does it belong to, and the summary the accountant files from
(taxable value, CGST, SGST, IGST) as a CSV.
"""

import csv
import io
import re

STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh",
    "23": "Madhya Pradesh", "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}
_SHAPE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def clean(gstin: str | None) -> str:
    return (gstin or "").strip().upper()


def check_letter(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _ALPHABET.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _ALPHABET[(36 - total % 36) % 36]


def gstin_problem(gstin: str | None) -> str | None:
    """None when the GSTIN is fine (or empty: it is optional), else what is wrong, in plain words."""
    g = clean(gstin)
    if not g:
        return None
    if len(g) != 15 or not _SHAPE.match(g):
        return "A GSTIN has 15 letters and digits, like 27AAPFU0939F1ZV."
    if g[:2] not in STATES:
        return f"{g[:2]} is not a state code."
    if check_letter(g[:14]) != g[14]:
        return "The last letter does not match: check the GSTIN for a typing mistake."
    return None


def state_of(gstin: str | None) -> str | None:
    g = clean(gstin)
    return STATES.get(g[:2]) if len(g) >= 2 else None


def summary_csv(summary: dict, start: str, end: str) -> str:
    """The GST summary for a period as CSV text (for the accountant)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Period", f"{start} to {end}"])
    w.writerow(["Taxable value", "CGST", "SGST", "IGST", "Total tax"])
    w.writerow([f"{float(summary.get(k) or 0):.2f}" for k in ("taxable_value", "cgst_total", "sgst_total", "igst_total", "total_tax")])
    return out.getvalue()
