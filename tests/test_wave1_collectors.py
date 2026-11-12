"""Wave-1 collectors parse saved public list pages (fetched on the runner on 12 Nov 2026, trimmed). No network."""
from pathlib import Path

S = Path(__file__).parent / "samples"


def test_dewa():
    from leads import dewa
    rows = dewa.parse((S / "dewa_open_tenders.html").read_text(encoding="utf-8"), "2026-11-12")
    assert len(rows) == 3                                   # the closed tender is left out
    r = rows[0]
    assert r["id"] == "DEWA-2422600124" and r["country"] == "ARE" and r["published"] == "2026-09-25" and r["deadline"] == "2026-11-12"
    assert "ASPHALT" in r["title"] and r["source_url"].startswith("https://www.dewa.gov.ae/") and r["fetched"] == "2026-11-12"
    assert "AED 1050" in r["access"]


def test_csg():
    from leads import csg
    rows = csg.parse((S / "csg_zbgg_page2.html").read_text(encoding="utf-8"), "2026-11-12")
    assert len(rows) == 10
    r = rows[0]
    assert r["id"].startswith("CSG-") and r["country"] == "CHN" and r["published"][:4] == "2026" and r["link"].startswith("https://www.bidding.csg.cn/zbgg/")
    assert r["buyer"] and r["title"] and r["lang"] == "zh"


def test_ccgp():
    from leads import ccgp
    rows = ccgp.parse((S / "ccgp_zygg_gkzb.html").read_text(encoding="utf-8"), "zygg/gkzb", "2026-11-12")
    assert len(rows) == 20
    r = rows[0]
    assert r["title"].startswith("国家冰球队") and r["buyer"] == "国家体育总局冬季运动管理中心" and r["province"] == "北京"
    assert r["published"] == "2026-11-12" and r["gov_level"] == "central" and r["link"] == "https://www.ccgp.gov.cn/cggg/zygg/gkzb/202611/t20261112_27672946.htm"


def test_lebanon():
    from leads import lebanon
    rows = lebanon.parse((S / "lebanon_ppa_tenders_en.html").read_text(encoding="utf-8"), "2026-11-12")
    assert len(rows) == 4
    r = rows[0]
    assert r["id"] == "LB-13506" and r["buyer"] == "Municipality of Ain Saade" and r["gov_level"] == "local"
    assert r["published"] == "2026-11-12" and r["deadline"] == "2026-12-28" and r["lang"] == "ar" and r["link"].endswith("/13506")


def test_cameroon():
    from leads import cameroon
    rows = cameroon.parse((S / "cameroon_armp_home.html").read_text(encoding="utf-8"), "2026-11-12")
    assert rows and all(r["id"].startswith("CM-AMI-") for r in rows)      # COMM and DEC-ATTR skipped
    r = rows[0]
    assert r["country"] == "CMR" and r["published"].startswith("2026-") and r["buyer"] and r["link"].startswith("https://armp.cm/details?")
