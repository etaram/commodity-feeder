# Logistics providers dataset

`logistics_providers.csv` is a research directory of logistics providers, official customs registries and official import-conformity programmes. It supports an Israeli international procurement and trading firm that ships commodities, power and infrastructure equipment (including heavy-lift and project cargo), defence and security goods, medical equipment and data-center equipment. Suppliers are mainly in China, India, Turkey, Europe and Israel. Buyers are mainly in Sub-Saharan Africa, MENA, South and Southeast Asia, Latin America, CIS and Central Asia, and Israel.

- Verification date: 2026-11-04 (the `verified` column on every row)
- Rows: 148
- Format: UTF-8 CSV with a header row; fields that contain commas are quoted; list fields are separated by semicolons

## Verification method

- Each row was checked against the organisation's own official website, or for registries and programmes against the issuing government body's website. The page used is in `source_url`.
- Third-party sites such as directories, news sites, rankings and LinkedIn were used only to find candidate names. They were never used as evidence.
- Figures come only from the official page. Where a page states nothing, the field says `not stated`.
- Some official sites block automated reading. For these rows, the existence of the organisation and the service was confirmed from pages that a domain-restricted search returned on the official domain, and the scale fields say so: Evergreen, Qatar Airways Cargo, EL AL Cargo, Chapman Freeborn, Transnet Port Terminals, the Nigeria Customs licensed-agents page and the Israel Tax Authority customs-agent list.
- `country_hq` uses the headquarters the site states, or the widely known registered headquarters. It is `not stated` where this was uncertain (deugro, Challenge Group, Chapman Freeborn, Freightos, SeaRates).

## Columns

| column | content |
|---|---|
| name | Full organisation, registry or programme name |
| short_name | Short label |
| category | forwarder, ocean_carrier, breakbulk, air_cargo, inspection, port_terminal, insurance, customs or platform |
| country_hq | ISO3 country code |
| services | Values from: FCL; LCL; breakbulk; heavy-lift/project cargo; RoRo; dry bulk; air freight; air charter; customs clearance; warehousing; inland trucking; rail; pre-shipment inspection; quality/quantity inspection; certification; marine cargo insurance; dangerous goods; defence cargo; cold chain; freight rates/quotes; door-to-door |
| cargo_types | Values from: containers; bulk commodities; project cargo; vehicles; perishables; hazardous; defence; medical; general |
| regions | Values from: Sub-Saharan Africa; Middle East & North Africa; South Asia; Southeast Asia; East Asia; Latin America; CIS & Central Asia; Europe; North America; Oceania; Israel; global |
| key_lanes | Trade lanes as stated. Inspection rows list the countries where the body runs programmes, or the appointed operators. |
| ports | Ports and airports served, as stated. Left empty if the source does not state them. |
| israel_presence | yes, with the office city where the site states it; otherwise not stated |
| defence_ok | yes, no, case by case or not stated: whether the organisation publicly states that it handles defence or military cargo |
| certifications | AEO, ISO, IATA, FIATA, TAPA and similar, only where stated |
| scale_note | One factual line taken from the official page |
| contact_url | Official contact or quote page |
| source_url | Official page used for verification |
| verified | 2026-11-04 |

## Counts per category

| category | rows |
|---|---|
| forwarder | 28 (includes 5 Israeli forwarders with customs brokerage) |
| customs | 24 (6 Israeli brokers or registries, 15 destination-market registries and associations, 3 compliance and defence or dangerous-goods specialists) |
| inspection | 23 (10 inspection companies, 13 official import programmes) |
| ocean_carrier | 15 (12 container lines, 3 RoRo carriers) |
| air_cargo | 14 |
| insurance | 13 (4 Israeli insurers) |
| breakbulk | 12 (8 heavy-lift and breakbulk operators, 2 dry bulk operators, 2 brokers) |
| port_terminal | 12 |
| platform | 7 |
| total | 148 |

## Customs layer

- **Israel.** Licensed brokers with their own sites: Fritz, UnitedXP, ISLINE, UBL (Ashdod, Haifa, Ben Gurion), Airgate, plus the forwarders with customs brokerage (Amit, Fridenson, Orian, Krief, AllCargo). The Israel Tax Authority register of customs agent corporations is on gov.il but could not be read automatically. No verified broker states an Eilat presence.
- **Destination registries and associations:**
  - Kenya: KRA list of about 1,139 licensed agents
  - Nigeria: Nigeria Customs Service licensed-agents page
  - Ghana: GRA Customs House Agent licensing
  - Tanzania: TRA licensing and CFA list
  - Uganda: URA clearing agents, and the UFFA association
  - Morocco: ADII list of active transitaires
  - Saudi Arabia: ZATCA licence check
  - UAE: Dubai Customs broker services
  - India: FFFAI
  - Vietnam: VLA member directory
  - Philippines: BOC accreditation lists
  - Colombia: DIAN agencias de aduanas
  - Brazil: Receita Federal list of despachantes
  - Kazakhstan: KGD register of customs representatives
- **Import programmes (category inspection):**
  - Kenya PVoC
  - Nigeria SONCAP
  - Ghana EasyPASS
  - Tanzania PVoC
  - Uganda PVoC
  - Ethiopia PVoC
  - Egypt GOEIC factory registration and Egypt ACI
  - Morocco PCA
  - Saudi SABER
  - UAE ECAS
  - India BIS QCO, CRS and FMCS
  - Cameroon BESC (an ECTN)

## Known gaps

- No verified official broker registry or association was found for Ethiopia or Egypt. The KIFWA (Kenya) website could not be confirmed as official, so the KRA register is used instead. For Ghana and Nigeria, the freight-forwarder bodies (GIFF, CRFFN) had no verifiable official site.
- No pre-shipment programme row was added for Vietnam, the Philippines, Colombia, Brazil or Kazakhstan. These countries rely on national certification (EAEU for Kazakhstan) rather than PSI, and this was not researched further.
- These organisations are not included because their official pages could not be read or did not confirm the service: TÜV SÜD, Yusen Logistics, Norden, Livingston (US and Canada only), Ashdod Port Company (site blocks automated reading), Doraleh Multipurpose Port, Agility (its forwarding business was sold to DSV), Shipco Transport and Unilog (no official site found), and the Volga-Dnepr successors.
- DB Schenker is folded into the DSV row because dbschenker.com project pages now redirect to dsv.com.
- Many global providers do not state their Israel presence on the pages checked, so `israel_presence` is `not stated`. This does not mean they are absent from Israel.

## Independent check (November 2026)

A second, independent pass re-checked all 148 rows field by field on the official pages. 25 wrong fields were corrected (for example Descartes is a customs software platform, not a broker; Redcliffe and SLG are defence-capable forwarders; Challenge is headquartered in Malta; Kenya PVoC now cites KEBS and its manual version 15). Fields that no official page could confirm, usually because the site refused automated reading, are listed per row in `check_note`. Raw results: `_verify_1_result.csv`, `_verify_2_result.csv`.
