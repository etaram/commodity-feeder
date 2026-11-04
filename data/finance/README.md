# Finance providers dataset

`finance_providers.csv` lists 133 institutions that finance, insure or grant-fund cross-border supply deals of the kind an Israeli international procurement and trading firm does. That means supplying goods, equipment and EPC packages to public tenders and large buyers, mainly in emerging markets.

## Verification

Every row was checked against the institution's own official website (or, for a programme, the official site of the agency that runs it) on 2026-11-04. The `source_url` column holds the page that was read.

Facts come only from those pages. Nothing was filled in from memory, so ratings, ticket sizes, costs and content rules are filled in only where the source states them. Otherwise they say `not stated` or are left empty.

Some official sites block automated reading: ASHRA, CESCE, China Exim, AfDB, EBRD and TDB. For these, the product page was confirmed on the official domain through search, but the page text could not be read. The `reputation_note` of each of these rows says so.

ASHRA's own site could not be loaded. Its facts come from its Berne Union member page.

SERV's facts come from the Swiss government SME portal (kmu.admin.ch).

## Columns

| column | meaning |
|---|---|
| name, short_name | full name and common abbreviation |
| category | ECA, DFI, multilateral, insurer, bank, fund or grant |
| country_hq | ISO3 code of the headquarters |
| owner | government, multilateral or private |
| products | semicolon list: buyer credit; supplier credit; pre-export finance; L/C confirmation; guarantees; working capital; credit insurance; political risk insurance; project finance; equity; grant; feasibility grant |
| sectors | semicolon list from the fixed sector names, or `all` |
| regions | semicolon list from the fixed region names, or `global` |
| eligibility | who can apply, in one line |
| content_rule | national content requirement as stated, `per supporting ECA` for ECA-backed bank lending, or `none stated` / `not stated` |
| defence_ok | yes, no, case by case or not stated, per the source |
| ticket_min_usd, ticket_max_usd | only when the source states a USD figure; amounts in other currencies are given in the text columns |
| typical_cost | pricing as publicly stated |
| rating | only when shown on the source page |
| reputation_note | size or track record as stated on the source |
| israel_link | `yes` with a reason; `no` with a reason when a source documents an exclusion; otherwise `none found on source` |
| apply_url, source_url | official product or contact page, and the page that was verified |
| verified | 2026-11-04 |

## Categories covered

| category | rows |
|---|---|
| ECA (export credit agencies and Eximbanks) | 38 |
| bank (commercial trade and export finance) | 28 |
| DFI (development finance institutions) | 18 |
| multilateral (MDBs and multilateral trade finance programmes) | 17 |
| insurer (political risk and credit insurance, public and private) | 15 |
| grant (feasibility and grant funding) | 11 |
| fund (specialist funds and platforms) | 6 |
| **total** | **133** |


## Independent verification (2026-11-04)
A second researcher, who had not seen the build, checked 116 of the 133 rows (every row with a stated ticket, cost,
rating, defence policy, content rule or Israel link, plus a sample of the rest) against the official pages.
21 fields were corrected (ratings, defence policies, content rules, costs, tickets stated in another currency).
Fields that could not be confirmed on an official page are listed per row in `check_note` and shown in the panel.
Results: `_verify_1_result.csv`, `_verify_2_result.csv`.
