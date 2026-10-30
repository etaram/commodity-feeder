"""Malaysia: MyProcurement (Ministry of Finance) tender advertisements. Needs a real browser; newest pages only."""
import datetime as dt
import html as H
import re

from .common import clean, log, polite, rolling, today
from .sectors import classify
from .stealth import pages

URL = "https://myprocurement.treasury.gov.my/advertisements/tender"
PAGES = 25


def _d(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def fetch():
    t, new, seen = today(), [], set()
    for page, b in enumerate(pages(URL, PAGES), 1):
        txt = H.unescape(re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " | ", b, flags=re.S)))
        blocks = re.split(r"Tarikh Pelawaan\s*:", txt)[1:]
        if not blocks:
            break
        got = 0
        for blk in blocks:
            def f(label):
                m = re.search(label + r"[\s|:]*([^|]*)", blk)
                return clean(m.group(1)) if m else ""
            no = f("No\\. Tender")
            title = clean(re.sub(r"\s*\|\s*", " ", blk.split("Kementerian", 1)[0].split(no, 1)[-1]).strip(" :|"))[:300] if no else ""
            close = _d(f("Tarikh Tutup Pelawaan"))
            if not no or no in seen or (close and close < t):
                continue
            seen.add(no); got += 1
            val = re.search(r"Harga Indikatif Jabatan[\s|:]*RM\s*([\d,\.]+)", blk)
            try:
                v = float(val.group(1).replace(",", "")) if val else ""
            except ValueError:
                v = ""
            sector, _ = classify(title)
            new.append({"id": "MY-" + re.sub(r"\W+", "-", no), "source": "MyProcurement (Malaysia)", "group": "", "sector": sector, "nature": f("Kategori Perolehan"),
                        "cpv": "", "classification": f("Kod Bidang")[:60], "country": "MYS", "buyer": (f("Agensi") or f("Kementerian"))[:120], "title": title,
                        "notice_type": "Tender", "stage": "tender", "access": "National (local registration / MOF code)", "published": str(_d(blk[:30]) or ""),
                        "deadline": str(close or ""), "value": v, "currency": "MYR" if v else "", "link": URL, "contact": "", "lang": "ms"})
        log.info("Malaysia page %d: %d blocks, %d new, first %s", page, len(blocks), got, (re.search(r"No\. Tender[\s|:]*([^|]*)", blocks[0]) or [0, ""])[1])
    rows, _ = rolling("malaysia", new)
    log.info("Malaysia new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
