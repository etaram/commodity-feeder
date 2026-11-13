"""Hong Kong Government Logistics Department e-Tender Box (ETB): open tender notices of Hong Kong government
departments, from the official open-data XML (data.gov.hk dataset hk-gld-gldetb-gldetb-tendernotice):
https://pcms2.gld.gov.hk/iportal/TenderNotice.xml : tender number, issue and closing date-time (Hong Kong time,
UTC+8), English subject, department, status, link. Status I = invitation. Contact fields (phone, e-mail, fax) are
not read. Licence: DATA.GOV.HK terms (free reuse, including commercial, with attribution)."""
import re
import xml.etree.ElementTree as ET

from .common import clean, log, quarantine_future, session, snapshot, today, valid_date
from .sectors import classify

URL = "https://pcms2.gld.gov.hk/iportal/TenderNotice.xml"
CONCESSION = re.compile(r"grant of (?:a )?(?:permit|licen[cs]e)|to operate|tenancy|sale of|disposal of", re.I)


def _tag(e):
    return e.tag.split("}")[-1]


def parse(xml_text, fetched):
    root = ET.fromstring(xml_text)
    rows = []
    for rec in root.iter():
        if _tag(rec) != "TenderNoticeRecord":
            continue
        f = {_tag(c): clean(c.text or "") for c in rec}
        no, subj = f.get("TenderNo", ""), f.get("SubjectEnglish", "") or f.get("SubjectChinese", "")
        if not no or not subj or f.get("Status", "I") != "I":
            continue
        dept = f.get("DepartmentEnglish") or f.get("IssuingDepartmentEnglish") or f.get("ProcuringDepartmentEnglish") or ""
        sector, how = classify(subj)
        conc = bool(CONCESSION.search(subj))
        rows.append({"id": "HKGLD-" + re.sub(r"[^A-Za-z0-9]+", "-", no)[:80].strip("-"), "source": "Hong Kong GLD e-Tender Box (open data)",
                     "group": "", "sector": sector, "nature": "", "cpv": "", "classification": how, "country": "HKG",
                     "buyer": (dept or "Hong Kong SAR Government")[:120], "title": subj[:300],
                     "notice_type": "Tender invitation" + (" (concession / licence, not a purchase)" if conc else "") + (" | addendum issued" if f.get("NewAddendumIndicator") == "Y" else ""),
                     "stage": "concession" if conc else "tender", "access": "Hong Kong government tender (WTO GPA where stated)",
                     "published": valid_date(f.get("IssueDateTime", "")), "deadline": valid_date(f.get("ClosingDateTime", "")),
                     "deadline_basis": "submission", "deadline_time": f.get("ClosingDateTime", "")[11:16] + " HKT",
                     "value": "", "currency": "", "link": f.get("Link") or "https://pcms2.gld.gov.hk/iprod/", "source_url": URL,
                     "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    r = session().get(URL, timeout=60)
    r.raise_for_status()
    t = str(today())
    rows, q = quarantine_future(parse(r.content, t), "hk_gld")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= t]
    keep, _ = snapshot("hk_gld", rows)
    log.info("Hong Kong GLD: %d open invitations (%d concessions labelled)", len(keep), sum(1 for x in keep if x["stage"] == "concession"))
    return keep, {"new": len(keep), "quarantined": q, "complete_snapshot": 1}
