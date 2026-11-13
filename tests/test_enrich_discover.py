import json

from leads import enrich_server as es
from leads import web_contacts as wc


def test_discover_appends_newer_record_and_logs_attempts(tmp_path, monkeypatch):
    rows = [{"key": "a|KEN", "supplier": "Acme Steel Ltd", "country": "KEN", "verdict": "no website on record", "tier": 1},
            {"key": "b|KEN", "supplier": "Nowhere Co", "country": "KEN", "verdict": "no website on record", "tier": 1},
            {"key": "c|KEN", "supplier": "Has Site", "country": "KEN", "website": "https://x.example", "verdict": "ok"}]
    (tmp_path / "site.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(wc, "discover", lambda n, c: "https://acmesteel.co.ke/" if n.startswith("Acme") else None)
    monkeypatch.setattr(es, "site_lane", lambda it: {"key": it["key"], "website": it["website"], "verdict": "ok", "name_match": "high"})
    st = es.discover_run(tmp_path, workers=2)
    assert st["tried"] == 2 and st["found"] == 1 and st["ok_high"] == 1
    lines = [json.loads(x) for x in (tmp_path / "site.jsonl").read_text().splitlines()]
    assert lines[-1]["key"] == "a|KEN" and lines[-1]["website_basis"].startswith("discovered")
    st2 = es.discover_run(tmp_path, workers=2)          # nothing tried twice
    assert st2.get("tried", 0) == 0
