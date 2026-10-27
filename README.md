# commodity-feeder

Twice-daily price feed for the **Commodities Tracker - 2,000** Google Sheet.

GitHub Actions runs `python -m feeder.run` at 05:40 and 21:10 UTC, collects prices from free
official/public sources, keeps the best price per Master row and commits:

- `data/prices.csv` - one row per Master row: price in USD, original price/currency, date, source, link, calculation
- `data/candidates.csv` - every candidate price from every source (audit trail)
- `data/run_log.json` - per-source status, counts, FX used

The sheet pulls `prices.csv` with `apps_script/ImportFeed.gs` (08:05 and 23:35 Asia/Jerusalem).

## Sources (selection rule: newest date wins, then source rank)

| key | source | covers | key needed |
|---|---|---|---|
| yahoo | Yahoo Finance chart API (yfinance backend) | ~35 CME/NYMEX/COMEX/ICE futures (layer A) | no |
| westmetall | LME official cash settlement via Westmetall | Cu, Al, Zn, Ni, Pb, Sn | no |
| cn_spot | 100ppi spot via AKShare | ~55 China spot commodities (metals, steel, chemicals, plastics, ag) | no |
| census | US Census international trade API | US import unit values, HS6 | optional `CENSUS_KEY` |
| comext | Eurostat Comext DS-045409 | EU extra-EU import unit values, HS6 | no |
| comtrade | UN Comtrade | unit values for rows still missing | optional `COMTRADE_KEY` |

FX: ECB reference rates via Frankfurter (fallback open.er-api.com).

Trade unit values are monthly with a 1-3 month lag and are labelled "Trade unit value" in the sheet.

## Run manually
Actions tab -> commodity-feed -> Run workflow (optional: `only` = `yahoo,cn_spot`).

## Keys (optional)
Settings -> Secrets and variables -> Actions -> New repository secret: `CENSUS_KEY`, `COMTRADE_KEY`.
