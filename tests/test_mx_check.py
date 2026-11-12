"""leads/mx_check.py: verdicts from saved DNS answers, resumable cache, counts for refine (no network)."""
import json

from leads import mx_check as M

# DNS answers as dnspython returned them on 12 Nov 2026 for public domains (MX hosts, NS hosts)
SAMPLES = {
    "siemens.com": (["mx1.siemens.c3s2.iphmx.com.", "mx2.siemens.c3s2.iphmx.com."], ["ns1.siemens.com."], True, False),
    "example-forsale.com": ([], ["ns1.sedoparking.com.", "ns2.sedoparking.com."], True, False),
    "nonexistent-supplier-xyz.com": ([], [], False, True),
    "webonly.co.ke": ([], ["ns1.host.co.ke."], True, False),
    "nullmx.example": (["."], ["ns1.x.net."], True, False),
}


def test_classify_saved_answers():
    v = {d: M.classify(d, *a[:3], nx=a[3]) for d, a in SAMPLES.items()}
    assert v["siemens.com"] == ("mx_ok", "mx1.siemens.c3s2.iphmx.com")
    assert v["example-forsale.com"][0] == "parked"
    assert v["nonexistent-supplier-xyz.com"] == ("no_mx", "nxdomain")
    assert v["webonly.co.ke"] == ("no_mx", "a_only")
    assert v["nullmx.example"] == ("no_mx", "null_mx")
    assert M.classify("yopmail.com", ["mx.yopmail.com"], [], True) == ("disposable", "")


def test_domains_and_known_providers():
    assert M.domains_of("Sales@ACME.co.za; info@acme.co.za , bad@@x") == ["acme.co.za", "acme.co.za"]
    assert M.lookup("gmail.com") == ("mx_ok", "known provider")


def test_run_is_resumable_and_feeds_counts(tmp_path):
    uni = tmp_path / "universe.csv"
    uni.write_text("supplier,country,email\nA,KEN,a@siemens.com\nB,KEN,b@webonly.co.ke\nC,KEN,c@siemens.com\nD,KEN,\n", encoding="utf-8")
    out = tmp_path / "mx.jsonl"
    calls = []

    def fake(d):
        calls.append(d)
        a = SAMPLES[d]
        return M.classify(d, *a[:3], nx=a[3])
    s1 = M.run(minutes=1, workers=2, universe=uni, out=out, lookup_fn=fake)
    assert s1["domains"] == 2 and s1["mx_ok"] == 1 and s1["no_mx"] == 1
    M.run(minutes=1, workers=2, universe=uni, out=out, lookup_fn=fake)
    assert sorted(calls) == ["siemens.com", "webonly.co.ke"]          # second run: everything cached
    assert len(out.read_text().splitlines()) == 2                      # compacted, one line per domain
    res = M.load_results(out)
    rows = [{"email": "a@siemens.com"}, {"email": "b@webonly.co.ke"}, {"email": "x@unchecked.org"}, {"email": ""}]
    assert M.summary(rows, res) == {"mx_ok": 1, "no_mx": 1, "unchecked": 1}
    assert M.verdict_for("x@unknown.io; a@siemens.com", res) == "mx_ok"
