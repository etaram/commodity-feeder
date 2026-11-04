# The brain: signals, entities, plays

Purpose of the system: find and close cross-border deals - physical commodities and equipment for infrastructure,
energy, defence and health - as principal, agent or partner of the winning contractor. Everything below serves
that, at near-zero running cost (deterministic collectors in GitHub Actions; AI only when a person clicks).

## Three layers

1. **Entities**: buyer, winner/supplier, country, commodity, project. Already in the public CSVs
   (buyers, competitors, countries, competition, markets, awards, tenders, supplier universe).
2. **Signals**: dated facts about an entity, each with a source link: an open tender, a planned project,
   an award, an import flow and its unit price, a price move, a repeat-purchase cycle, a news item.
3. **Plays**: a deal thesis the engine writes from signals, with the role Sinder would take, the evidence,
   a value where the source states one, and one next step. `leads/plays.py` -> `data/leads/plays.csv`.

| Play | Signals combined | Role | Why it is alpha |
|---|---|---|---|
| Fit tender | deal fit (leads/dealfit.py) | direct bid / partner | continuous rank built for a sourcing firm, with why and flags |
| Supply the winner | repeat winner in a goods sector + proven Asian exporters in that sector | sub-supplier | the winner is a customer, not a competitor; nobody sells to him from a tender feed |
| Arbitrage gap | a country's import unit value well above the benchmark + exporters for that HS line | principal | price gap by product and country, from customs data, not from a tender |
| Pre-tender approach | buyer buys the same sector every year, next cycle due in 90 days | agent / direct | first in the room, months before 20 bidders |
| Planned project | IFI project approved, procurement not yet out | partner / sub-supplier | lead time measured in months |

## Country intelligence (`/api/panel/country?c=ISO3`)
One page per country from the same layers: open tenders by sector and value, international-open share, planned
projects, top buyers and their cycles, who wins (foreign share), what the country imports and at what price,
plays for the country, price trends for its commodities, risk and trade-agreement notes, and the week's business
news (GDELT, free, no key; `leads/gdelt.py`). Countries the owner watches get a weekly digest.

## Learning from the owner
Opens, searches, "relevant / not relevant" marks and pursuits are logged already. `tools/fit_calibrate.py`
compares the deal-fit rank with those marks and reports which rules disagree most; the constants in dealfit.W
are changed by hand, with the report as evidence, never silently.

## Sources that do not exist in the system yet (next)
- IFI procurement plans (World Bank STEP, AfDB, ADB): packages, amounts and dates before the tender.
- National budgets (capex lines) once a year, AI-read on request.
- GLEIF LEI relationships: subsidiaries folded into groups.
- The owner's own network (LinkedIn export in a private tab): "you know someone at this buyer".
- Exchange filings RSS (SZSE, BSE, NASDAQ) for listed partners and winners.
- Freight and FX indexes (Freightos FBX, ECB) feeding the margin model.

## Reaching markets and customers the system does not see today (2026-11-04)

What is missing today: private-sector buyers (no tender), portals that block foreign IPs, markets without an
open portal, and the context (news, geopolitics, experts) that says where demand is moving. Four routes, cheapest first:

1. **The news as a buyer feed** (built: `leads/briefing.py`). A company named as building, expanding, winning or
   financing something is a buyer or an EPC before any tender exists. Items become "news lead" plays with the
   article as evidence. Sources: Google News RSS topic queries shipped with the code, plus the owner's own feeds in
   the sheet tab Briefing Sources: podcasts (show notes), newsletters (Substack feeds), YouTube channels (feed),
   expert blogs. No AI in collection.
2. **The daily world brief** (built: `/api/panel/brief`). One Haiku call a day over the collected items, cached
   for everyone, every line cites its source, in Hebrew or English. Cost under $0.10 a day.
3. **Buyers behind the money**: IFI procurement plans (World Bank STEP, AfDB, ADB), listed companies' exchange
   filings (SZSE, BSE, Tadawul, NSE Kenya RSS), national budgets' capex lines. All free; next slices.
4. **Portals that block foreign IPs** (Zambia captcha, some Gulf and Latin portals): GitHub Actions runs only from
   US addresses. The cheapest fix is a free-tier VM in the right region (Oracle Cloud "always free", Frankfurt,
   Jeddah or Mumbai) running the same collectors on a cron and pushing to the repo. Needs the owner's account; no
   code change beyond a runner label. Paid alternative: a residential proxy, not recommended.

What the system will still not have: customs records with company names outside the US (Panjiva, Volza: paid),
private tenders that are never published, and anyone's intent before it is written somewhere. Those come from
people: the My Network tab and the plays' "next step" are built to put the owner in front of them first.
