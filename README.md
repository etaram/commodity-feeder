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
