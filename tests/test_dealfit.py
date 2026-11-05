"""Regression checks for leads/dealfit.py (spec section 12). Run: python -m tests.test_dealfit"""
from leads.dealfit import apply, fit

B = {"title_en": "Supply of transformers", "sector": "Power & electrical equipment", "region": "Sub-Saharan Africa", "country": "KEN",
     "est_value_usd": "2000000", "days_left": "30", "priority_ev_usd": "50000", "addressable_share": "1", "decision": "Pursue"}


def check():
    o = fit({**B, "access": "international competitive bidding"})[0]
    assert fit({**B, "access": "not open to foreign bidders"})[0] < o, "negation must not read as open"
    assert "restriction applies" in fit({**B, "access": "national competitive bidding (NCB)", "source": "World Bank"})[2], "IFI must not override a restriction"
    assert "unknown" in fit({k: v for k, v in B.items() if k != "addressable_share"} | {"access": "international"})[2], "missing goods share is not full goods"
    assert fit({**B, "access": "international", "priority_ev_usd": "nan", "est_value_usd": "inf"})[0] < 100, "non-finite input must not saturate"
    assert fit({**B, "access": "international", "days_left": "-3"})[0] == 0, "expired notice scores 0"
    assert "licence" not in fit({**B, "access": "international", "title_en": "plasma cutting machine"})[2], "plasma cutting is not plasma"
    assert "licence" not in fit({**B, "access": "international", "title_en": "blood pressure monitors"})[2], "blood pressure monitors are not blood"
    assert "local partner" not in fit({**B, "access": "international"}, {"partners": {"KEN": False}})[1], "false partner is not a partner"
    rows = [dict(B, access="international", score="55")]
    apply(rows); apply(rows)
    assert rows[0]["base_score"] == "55", "repeated apply keeps the original score"
    print("dealfit: all checks passed")


if __name__ == "__main__":
    check()
