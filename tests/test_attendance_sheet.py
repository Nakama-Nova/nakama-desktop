from services import attendance_sheet as sheet


def rec(uid, day, status, name="Ravi"):
    return {"user_id": uid, "date": day, "status": status, "user": {"full_name": name}}


def test_the_month_grid_counts_days_and_takes_the_best_record_of_a_day():
    users = [{"id": "u1", "full_name": "Ravi"}, {"id": "u2", "full_name": "Anil"}]
    recs = [
        rec("u1", "2026-11-01", "present"), rec("u1", "2026-11-02", "half-day"), rec("u1", "2026-11-03", "absent"),
        rec("u1", "2026-11-03", "present"),  # checked in later the same day: present wins
        rec("u1", "2026-11-04", "leave"), rec("u1", "2026-10-31", "present"),  # another month: left out
        rec("u3", "2026-11-05", "present", "Gone"),  # a person no longer on the list still shows
    ]
    s = sheet.build_sheet(users, recs, 2026, 11)
    assert s["days"] == 30 and [r["name"] for r in s["rows"]] == ["Anil", "Gone", "Ravi"]
    ravi = s["rows"][2]
    assert ravi["cells"] == {1: "P", 2: "½", 3: "P", 4: "L"} and ravi["worked"] == 2.5 and ravi["leave"] == 1
    assert s["rows"][0]["worked"] == 0
    out = sheet.to_csv(s, 2026, 11)
    assert out.splitlines()[1].startswith("Name,1,2,3") and "Ravi,P,½,P,L" in out and out.splitlines()[-1].endswith("2.5,0,1")


def test_the_sheet_dialog_fills_a_grid_and_moves_between_months(qapp):
    from ui.attendance_sheet import MonthSheetDialog

    class Svc:
        calls = []

        def get_all_attendance(self, user_id, start, end):
            self.calls.append((start, end))
            return [rec("u1", start[:8] + "02", "present")]

    svc = Svc()
    d = MonthSheetDialog(None, svc, [{"id": "u1", "full_name": "Ravi"}])
    assert d.table.item(0, 1).text() == "P" and d.table.verticalHeaderItem(0).text() == "Ravi"
    d._year, d._month = 2026, 12
    d._move(1)
    assert (d._year, d._month) == (2027, 1) and svc.calls[-1] == ("2027-01-01", "2027-01-31")
