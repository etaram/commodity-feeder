"""Indonesia: open tenders (Tender, not Non Tender) from the national SPSE e-procurement system run by LKPP
(spse.inaproc.id/<lpse>/lelang): one SPSE instance per ministry, province, regency and city (about 640).

Access (checked 2026-11-14): spse.inaproc.id/robots.txt allows every LPSE path (it lists them) with Crawl-delay 1;
the package list is the page's own public DataTables feed (POST /<lpse>/dt/lelang with the page's form token, no
login), and each package has a public schedule page (/<lpse>/lelang/<id>/jadwal). We wait at least 1 s between calls.

OPEN = a package whose current stage (tahapan) is still before bid opening, and whose FIRST submission stage (upload
of the bid or of the qualification documents) ends today or later: that end is the deadline. A pre-qualification whose
qualification upload has closed is no longer open to new bidders and is skipped. The list is read every run; a
package's schedule is fetched once and kept (rolling cache) until its deadline passes."""
import datetime as dt
import json
import os
import re
import time

import requests

from .common import CACHE, clean, log, quarantine_future, session, today
from .sectors import classify

HOST = "https://spse.inaproc.id"
BUDGET_S = int(os.environ.get("INDONESIA_BUDGET_S", "700"))
GAP = 1.05          # robots.txt Crawl-delay: 1
PAGE = 100
MAX_PAGES = 15
MONTHS = {m: i + 1 for i, m in enumerate(["januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus",
                                          "september", "oktober", "november", "desember"])}
CLOSED = re.compile(r"pembukaan|evaluasi|pembuktian|penetapan|pemenang|sanggah|klarifikasi|negosiasi|penandatanganan|"
                    r"selesai|gagal|batal|ditutup|penunjukan|kontrak|reverse auction|e-reverse", re.I)
OPEN = re.compile(r"pengumuman|pendaftaran|download|penjelasan|upload|pemasukan|kirim|penyampaian", re.I)
SUBMIT = re.compile(r"(upload|pemasukan|kirim|penyampaian)\b.*(penawaran|kualifikasi)|(penawaran|kualifikasi).*(upload|pemasukan)", re.I)
NATURE = {"pengadaan barang": "goods", "pekerjaan konstruksi": "works", "jasa lainnya": "services"}
STATE = CACHE / "indonesia_jadwal.jsonl"   # one line per package: {"k": key, ...}


class _Polite:
    """One host, one call at a time, at least GAP seconds apart. No relay: a refusal is reported, not routed around."""
    def __init__(self):
        self.s = session()
        self.s.headers["Accept-Language"] = "id-ID,id;q=0.9,en;q=0.8"
        self.last, self.calls, self.errors = 0.0, 0, 0

    def _wait(self):
        d = time.time() - self.last
        if d < GAP:
            time.sleep(GAP - d)
        self.last = time.time(); self.calls += 1

    def get(self, url, **kw):
        self._wait()
        return requests.Session.get(self.s, url, timeout=kw.pop("timeout", 40), **kw)

    def post(self, url, **kw):
        self._wait()
        return requests.Session.post(self.s, url, timeout=kw.pop("timeout", 40), **kw)


def lpse_codes(c):
    r = c.get(HOST + "/robots.txt")
    r.raise_for_status()
    codes = []
    for m in re.finditer(r"(?im)^\s*Allow:\s*/([a-z0-9][a-z0-9_-]*)\s*$", r.text):
        if m.group(1) not in codes:
            codes.append(m.group(1))
    return codes


def id_date(s):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", s or "")
    if not m or m.group(2).lower() not in MONTHS:
        return "", ""
    try:
        d = dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return "", ""
    return str(d), (f"{int(m.group(4)):02d}:{m.group(5)} WIB" if m.group(4) else "")


def parse_jadwal(html):
    """(deadline, time, stage name) of the first submission stage on a schedule page, or ('', '', '')."""
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [clean(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(cells) < 4:
            continue
        name = next((c for c in cells if SUBMIT.search(c)), "")
        if not name:
            continue
        dates = [id_date(c) for c in cells]
        dates = [d for d in dates if d[0]]
        if len(dates) >= 2:
            return dates[1][0], dates[1][1], name
        if dates:
            return dates[0][0], dates[0][1], name
    return "", "", ""


def dt_params(start, length):
    p = {"draw": 1, "start": start, "length": length, "search[value]": "", "search[regex]": "false",
         "order[0][column]": 5, "order[0][dir]": "desc"}
    for i in range(6):
        p[f"columns[{i}][data]"] = i
        p[f"columns[{i}][searchable]"] = "true"
        p[f"columns[{i}][orderable]"] = "true"
    return p


def read_lpse(c, code, years, diag):
    """All packages listed by one LPSE for the given budget years whose stage looks open: [(row list, year)]."""
    r = c.get(f"{HOST}/{code}/lelang")
    if r.status_code != 200:
        raise RuntimeError(f"list page HTTP {r.status_code}")
    tok = re.search(r"authenticityToken\s*=\s*'([0-9a-f]+)'", r.text)
    if not tok:
        raise RuntimeError("no form token on the list page")
    out = []
    for y in years:
        for pg in range(MAX_PAGES):
            q = dt_params(pg * PAGE, PAGE); q["authenticityToken"] = tok.group(1)
            rr = c.post(f"{HOST}/{code}/dt/lelang", params={"tahun": y}, data=q,
                        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{HOST}/{code}/lelang"})
            if rr.status_code != 200:
                raise RuntimeError(f"dt/lelang HTTP {rr.status_code}")
            j = rr.json()
            data = j.get("data") or []
            if not diag.get("sample") and data:
                diag["sample"] = [str(x)[:60] for x in data[0]]
                diag["total_first"] = j.get("recordsTotal")
            n_open = 0
            for row in data:
                stage = clean(str(row[3] if len(row) > 3 else ""))
                if OPEN.search(stage) and not CLOSED.search(stage):
                    out.append((row, y)); n_open += 1
            total = int(j.get("recordsFiltered") or j.get("recordsTotal") or 0)
            if (pg + 1) * PAGE >= total or not data or (pg >= 1 and n_open == 0):
                break
    return out


def money(s):
    """'291,7 M' (miliar) / '850 Jt' (juta) / '1.234.567' -> rupiah, else 0."""
    s = clean(str(s or "")).replace(" ", "")
    m = re.match(r"([\d.,]+)([A-Za-z]*)", s)
    if not m:
        return 0
    num, unit = m.group(1), m.group(2).lower()
    if unit:
        num = num.replace(".", "").replace(",", ".")
    else:
        num = num.replace(".", "").replace(",", ".")
    try:
        v = float(num)
    except ValueError:
        return 0
    return round(v * {"m": 1e9, "t": 1e12, "jt": 1e6, "rb": 1e3}.get(unit, 1))


def fetch():
    c, t0, t = _Polite(), time.time(), today()
    ts = str(t)
    state = {}
    if STATE.exists():
        try:
            for line in STATE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    x = json.loads(line); state[x.pop("k")] = x
        except (ValueError, KeyError):
            state = {}
    codes = lpse_codes(c)
    years = [t.year, t.year + 1]
    diag, failed, cut, done = {}, 0, False, 0
    found = {}
    for code in codes:
        if time.time() - t0 > BUDGET_S * 0.55:
            cut = True; break
        try:
            for row, y in read_lpse(c, code, years, diag):
                found[f"{code}:{row[0]}"] = (code, row)
            done += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            if failed <= 5:
                log.warning("Indonesia SPSE %s: %s", code, str(e)[:120])
            if failed >= 25 and done == 0:
                break
    log.info("Indonesia SPSE: %d of %d LPSE lists read, %d failed, %d packages at an open stage; sample row %s (total %s)",
             done, len(codes), failed, len(found), diag.get("sample"), diag.get("total_first"))
    rows, fetched_sched, no_deadline, past = [], 0, 0, 0
    for key, (code, row) in found.items():
        pid = str(row[0])
        st = state.get(key)
        if not st:
            if time.time() - t0 > BUDGET_S:
                cut = True; continue
            try:
                r = c.get(f"{HOST}/{code}/lelang/{pid}/jadwal")
                fetched_sched += 1
                if r.status_code != 200:
                    continue
                dl, hm, name = parse_jadwal(r.text)
            except Exception as e:  # noqa: BLE001
                log.warning("Indonesia SPSE jadwal %s: %s", key, type(e).__name__); continue
            st = {"deadline": dl, "time": hm, "stage": name, "seen": ts}
            state[key] = st
            if fetched_sched == 1:
                log.info("Indonesia SPSE first schedule: %s", st)
        dl = st.get("deadline") or ""
        if not dl:
            no_deadline += 1; continue
        if dl < ts:
            past += 1; continue
        title = clean(str(row[1]))
        if len(row) > 8:
            kat = clean(str(row[8]))
        else:
            kat = ""
        hps = money(row[4] if len(row) > 4 else "")
        sector, how = classify(title)
        rows.append({"id": f"ID-SPSE-{code}-{pid}", "source": "SPSE INAPROC (Indonesia, LKPP)", "group": "", "sector": sector,
                     "nature": NATURE.get(kat.lower(), ""), "cpv": "", "classification": how, "country": "IDN",
                     "buyer": clean(str(row[2]))[:120], "title": title[:300],
                     "notice_type": "Tender" + (f" | {kat}" if kat else "") + f" | LPSE {code}", "stage": "tender",
                     "access": "Indonesian public procurement (bidders register on SIKaP/SPSE; Indonesian-language documents)",
                     "published": "", "deadline": dl, "deadline_basis": "submission: " + st.get("stage", "")[:60],
                     "deadline_time": st.get("time", ""),
                     "value": hps or "", "currency": "IDR" if hps else "",
                     "link": f"{HOST}/{code}/lelang/{pid}/pengumumanlelang", "source_url": f"{HOST}/{code}/lelang",
                     "fetched": ts, "contact": "", "lang": "id"})
    # keep schedules only for packages still listed open, so the state file does not grow forever
    state = {k: v for k, v in state.items() if k in found or (v.get("deadline") or "9999") >= ts and v.get("seen", ts) >= str(t - dt.timedelta(days=60))}
    CACHE.mkdir(parents=True, exist_ok=True)
    STATE.write_text("".join(json.dumps({"k": k, **v}, ensure_ascii=False, sort_keys=True) + "\n" for k, v in sorted(state.items())),
                     encoding="utf-8")
    if not rows and not found:
        raise RuntimeError("Indonesia SPSE: no package read; previous cache kept")
    rows, q = quarantine_future(rows, "indonesia")
    from .common import rolling, snapshot
    complete = not cut and failed == 0
    keep, _ = (snapshot if complete else rolling)("indonesia", rows)
    log.info("Indonesia SPSE: %d open tenders with a deadline (%d calls, %d schedules fetched, %d without a submission "
             "stage, %d past, %s)", len(keep), c.calls, fetched_sched, no_deadline, past,
             "cut at the time budget" if cut else "all lists read")
    return keep, {"new": len(rows), "calls": c.calls, "lpse_read": done, "lpse_failed": failed, "quarantined": q,
                  "schedules_fetched": fetched_sched, "complete_snapshot": 1 if complete else 0, "deep_link": 1}
