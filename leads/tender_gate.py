"""Quality gate v1 for open tenders (owner, 13-14 Nov 2026: a blind sample of 20 passed only 4; quality decides).

An open tender is VERIFIED only when every condition holds, each from what the notice itself carries:
  country   a valid ISO 3166 alpha-3 code
  buyer     a named buying organisation (not empty, not a placeholder such as 'not confirmed')
  link      a link that opens THIS notice on the official site, not a portal home or a generic list page
  title     a real title (at least 8 characters)
  scope     not petty local works (Indian local civil works are labelled by leads.local_works)
  stage     a tender in its bidding period (not a plan, an exemption, a concession, a disposal or a sale)
The gate never deletes a row: it writes 'verified' or 'unverified: <reasons>' in the row's quality column, and the
counts by reason go to the public log. The VERIFIED OPEN count is the one measured against the targets.
"""
import re

from .quality_gate import ISO_CODES

VERSION = "tender-gate-1.0 (2026-11-14)"
GENERIC_LINK = re.compile(r"FrontEndLatestActiveTenders|FrontEndTendersByOrganisation|page=Home\b|portal\.htm$|"
                          r"/tenders/?$|/opportunities/?$|/bids/?$|advancedSearchBid\.xhtml|/iprod/?$|/prosolicitation/?$", re.I)
GENERIC_BUYER = re.compile(r"not confirmed|^public agency,|^unknown|^n/?a$|^-+$", re.I)
OPEN_STAGES = {"tender", ""}


def reasons(r):
    out = []
    c = r.get("country") or ""
    if not re.fullmatch(r"[A-Z]{3}", c) or (ISO_CODES and c not in ISO_CODES):
        out.append("country")
    b = (r.get("buyer") or "").strip()
    if not b or GENERIC_BUYER.search(b):
        out.append("buyer")
    link = (r.get("link") or "").strip()
    if not link.startswith("http") or GENERIC_LINK.search(link):
        out.append("link")
    if len((r.get("title") or "").strip()) < 8:
        out.append("title")
    if "local civil works" in (r.get("notice_type") or ""):
        out.append("local_works")
    if (r.get("stage") or "") not in OPEN_STAGES:
        out.append("stage")
    return out


def mark(r):
    bad = reasons(r)
    r["quality"] = "verified" if not bad else "unverified: " + ",".join(bad)
    return not bad
