"""Enrichment site lane in several processes (--procs): every key is read by exactly one shard; process 0 sees the
other shards' lines (status counts and the other lanes) by reading site.jsonl back; a restart skips keys already read."""
import json

from leads import enrich_server as es


def _queue(d, n):
    with open(d / "queue.jsonl", "w") as f:
        for i in range(n):
            f.write(json.dumps({"key": f"k{i}", "name": f"Co {i}", "country": "KEN", "website": f"https://c{i}.example", "tier": 0, "ev": 0}) + "\n")


def test_shards_cover_each_key_once(tmp_path, monkeypatch):
    _queue(tmp_path, 60)
    seen = []
    monkeypatch.setattr(es, "site_lane", lambda it: (seen.append(it["key"]), {"key": it["key"], "verdict": "ok", "name_match": "high", "checked_at": "t"})[1])
    monkeypatch.setattr(es, "export", lambda d: None)
    monkeypatch.setattr(es, "fill_rates", lambda d: {})
    es.run(tmp_path, 4, ("site",), shard=1, nshards=3, child=True)
    es.run(tmp_path, 4, ("site",), shard=2, nshards=3, child=True)
    es.run(tmp_path, 4, ("site",), shard=0, nshards=3)
    assert sorted(seen) == sorted(f"k{i}" for i in range(60)) and len(seen) == 60
    lines = (tmp_path / "site.jsonl").read_text().splitlines()
    assert len(lines) == 60 and all(json.loads(x)["key"] for x in lines)
    st = json.loads((tmp_path / "status.json").read_text())
    assert st["done"] == 60 and st["remaining"] == 0
    seen.clear()
    es.run(tmp_path, 4, ("site",), shard=1, nshards=3, child=True)     # restart: nothing read twice
    assert seen == []
