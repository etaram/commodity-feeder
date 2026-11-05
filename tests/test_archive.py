"""Pure checks for leads/archive.py."""
from datetime import date

from leads.archive import is_closed, split

T = date(2026, 11, 5)


def test_split():
    rows = [{"id": "A", "days_left": -3, "stage": "tender"}, {"id": "B", "days_left": -3, "stage": "tender"},
            {"id": "C", "days_left": 4, "stage": "tender"}, {"id": "D", "days_left": -10, "stage": "planned"},
            {"id": "E", "days_left": "", "deadline": "2026-10-01", "stage": "tender"}, {"id": "F", "days_left": "", "deadline": "", "stage": "tender"}]
    keep, gone = split(rows, {"B"}, T)
    assert [r["id"] for r in gone] == ["A", "E"]  # closed and not ours
    assert [r["id"] for r in keep] == ["B", "C", "D", "F"]  # ours, open, planned, no deadline
    assert not is_closed({"days_left": 0, "stage": "tender"}, T)  # closes today: still open


if __name__ == "__main__":
    test_split()
    print("archive: all checks passed")
