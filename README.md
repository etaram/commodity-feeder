# commodity-feeder

Twice-daily price feed for the **Commodities Tracker - 2,000** Google Sheet.

GitHub Actions runs `python -m feeder.run` at 05:40 and 21:10 UTC, collects prices from free
official/public sources, keeps the best price per Master row and commits:

- `data/prices.csv` - one row per Master row: price in USD, original price/currency, date, source, link, calculation
- `data/candidates.csv` - every candidate price from every source (audit trail)
- `data/run_log.json` - per-source status, counts, FX used

The sheet pulls `prices.csv` with `apps_script/ImportFeed.gs` (08:05 and 23:35 Asia/Jerusalem).

## Sources (selection: prices within 7 days of the newest count as current; among those the better-ranked source wins)

| rank | key | source | covers | key needed |
|---|---|---|---|---|
| 1 | yahoo | Yahoo Finance chart API (yfinance backend) | ~33 CME/NYMEX/COMEX/ICE futures (layer A) | no |
| 2 | westmetall | LME official cash settlement via Westmetall | Cu, Al, Zn, Ni, Pb, Sn | no |
| 2 | em_global | Eastmoney international futures board (AKShare) | ICE gasoil, Newcastle coal, Bursa palm oil, OSE rubber + backups | no |
| 3 | eu_agri | European Commission Agri-food Data Portal API | ~65 EU market prices: dairy, oilseeds, olive oil, meat, eggs, cereals, sugar, fruit & veg | no |
| 3 | dtn | DTN Retail Fertilizer Trends (weekly) | DAP, MAP, potash, urea, 10-34-0, anhydrous, UAN32 | no |
| 3 | ssb | Statistics Norway table 03024 | farmed salmon export price, fresh and frozen | no |
| 4 | scrapmonster | ScrapMonster / Institute for Rare Earths and Metals | ~34 minor metals, alloys, ores | no |
| 4 | smi | Strategic Metals Invest | Hf, Re, Sb, Bi, Te | no |
| 5 | cn_spot | 100ppi spot via AKShare | ~60 China domestic spot prices (VAT incl.) | no |
| 7 | census | US Census international trade API | US import unit values, HS6 | `CENSUS_KEY` (required since 2026) |
| 8 | comext | Eurostat Comext DS-045409 | EU extra-EU import unit values, HS6, ~1,900 codes | no |
| 9 | comtrade | UN Comtrade (median of CN/JP/KR/IN/BR importers) | rows still missing | optional `COMTRADE_KEY` |

FX: ECB reference rates via Frankfurter (fallback open.er-api.com).

## Benchmark model (one designated benchmark per commodity)
`data/benchmark_registry.csv` (built by `tools/build_registry.py`) assigns every Master row ONE benchmark:
the most reliable tier available (T1 exchange > T2 official market reporting > T3 industry assessment >
T4 trade statistics); on a tie the automated source wins. Rows whose best benchmark has no free automated
source (Trading Economics exchange quotes, World Bank, China NBS, USDA, GDT, Spices Board) are `manual`:
the sheet keeps their price and the scheduled task refreshes them from the same source; the feed price is
shown only as the check price. HS codes that are exactly an exchange-traded good take the exchange price
converted to the HS unit (`derived`). China spot prices are ex-VAT (13%, 9% for farm goods and fertiliser).

Sheet integration: each run writes `data/import/master_stage.csv` (G..P, R, T, U..Y, AA per Master row) and
`data/import/history_stage.csv`. In the sheet, hidden tabs Feed_Stage (IMPORTDATA) and Feed_Merge (formulas
that keep manual benchmarks) are copied into Master with one copyPaste batch, by the scheduled task or by
`apps_script/ImportFeed.gs`. Sources tab = registry of sources with live counts and Source_Health status.

## Quality control (column `quality`, shown in the sheet as a `[QA: ...]` note)
- plausibility bounds per unit (rejected)
- cross-source disagreement > 3x among candidates of the same row
- day-over-day move > 40% for daily sources
- Census: dominant unit must cover >= 60% of import value; Comtrade: importer unit values within 5x

## Scout: scrapers + source monitor
`feeder/sources/scrapers.py` holds the HTML/API scrapers; items a scraper sees but cannot map are saved to
`data/raw/unmapped_<source>.csv`. `feeder/monitor.py` writes `data/source_health.csv` after every run:
feed sources get OK / DEGRADED / STALE / DOWN; watched release pages (World Bank, NBS, ICO, FAO, GDT, USDA, IMF, LME,
Spices Board, MPOB) get CHANGED when their published data changes. The sheet shows it in the Source_Health tab.

## Discovery probe
`tools/probe_urls.txt` + the `probe` workflow fetch any URL from GitHub's network and commit the response to
`data/probe/` - used to inspect APIs/pages before writing a parser.

## Run manually
Actions tab -> commodity-feed -> Run workflow.

## Keys
Settings -> Secrets and variables -> Actions -> New repository secret: `CENSUS_KEY`, `COMTRADE_KEY`.

## Leads engine (`leads/`, workflow `leads.yml`, every 4 hours)

Separate Google Sheet "Leads Engine - Tenders & Importers" reads `data/leads/*.csv` with IMPORTDATA.

| Source | What it gives | Access |
|---|---|---|
| TED API v3 (EU) | Open contract notices for supplies, matched to commodity groups by CPV | free, no key |
| World Bank procurement notices | Goods tenders in World Bank financed projects, by keyword | free, no key |
| mr.gov.il | Open Israeli government tenders in commodity categories | public site |
| ImportYeti HS pages | Top US importers and their foreign suppliers per HS heading (US Customs bills of lading) | public site, ~24 headings per run, refresh every 14 days |

`leads/taxonomy.py` maps each commodity group to HS chapters, CPV codes, keywords and mr.gov.il categories, and to the tracker rows used as the price benchmark.
