"""
services/attendance_sheet.py

A month of attendance as a grid: one row per person, one column per day. Present (P),
half-day (½), absent (A), on leave (L) and holiday (•), with the days worked in the last
column. Built from the server's attendance records, and written out as CSV for the accountant.
"""

import calendar
import csv
import io

CODES = {"present": "P", "half-day": "½", "absent": "A", "leave": "L", "holiday": "•"}
WORKED = {"P": 1.0, "½": 0.5}


def build_sheet(users: list[dict], records: list[dict], year: int, month: int) -> dict:
    """{"days": n, "rows": [{"user_id", "name", "cells": {day: code}, "worked", "absent", "leave"}]}
    Several records on one day (checked in twice): the best one counts (present over half over absent)."""
    days = calendar.monthrange(year, month)[1]
    prefix = f"{year:04d}-{month:02d}-"
    rank = {"A": 0, "L": 1, "•": 1, "½": 2, "P": 3}
    names = {str(u.get("id")): u.get("full_name") or u.get("username") or "" for u in users}
    cells: dict[str, dict[int, str]] = {}
    for r in records:
        day = str(r.get("date") or "")
        code = CODES.get(r.get("status"))
        if not day.startswith(prefix) or not code:
            continue
        uid = str(r.get("user_id") or "")
        names.setdefault(uid, (r.get("user") or {}).get("full_name") or "")
        row = cells.setdefault(uid, {})
        d = int(day[8:10])
        if d not in row or rank[code] > rank[row[d]]:
            row[d] = code
    rows = []
    for uid in sorted(set(names) | set(cells), key=lambda u: names.get(u, "").lower()):
        c = cells.get(uid, {})
        rows.append({
            "user_id": uid, "name": names.get(uid) or "(former staff)", "cells": c,
            "worked": sum(WORKED.get(v, 0.0) for v in c.values()),
            "absent": sum(1 for v in c.values() if v == "A"), "leave": sum(1 for v in c.values() if v == "L"),
        })
    return {"days": days, "rows": rows}


def to_csv(sheet: dict, year: int, month: int) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Attendance", f"{calendar.month_name[month]} {year}"])
    w.writerow(["Name"] + list(range(1, sheet["days"] + 1)) + ["Days worked", "Absent", "Leave"])
    for r in sheet["rows"]:
        w.writerow([r["name"]] + [r["cells"].get(d, "") for d in range(1, sheet["days"] + 1)] + [f"{r['worked']:g}", r["absent"], r["leave"]])
    return out.getvalue()
