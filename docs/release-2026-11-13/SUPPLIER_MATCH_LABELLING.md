# Supplier match: labelling guide

You judge whether each company the search returned could really supply what was asked, without seeing the
matcher's own verdict.

## Files (Google Drive, folder `Sinder-Eval/<timestamp>/`)

- `rows.jsonl` - one line per returned supplier: `set`, `query_id`, `query`, `rank`, `supplier`, `country`, `type`,
  `evidence` (what the matcher read about the company), `website`, `has_contact`. This is the file you label.
- `tenders.jsonl` - for ids `T01`-`T30`: the tender title, sector and stratum (`goods`, `non_goods`, `mixed`).
- `verdicts.jsonl`, `human_labels.jsonl`, `summary.json` - for scoring only. Do not read them while labelling.

## What to write

One line per row you judged, in `labels.jsonl` (or a CSV with the same four columns):

    {"query_id": "Q17", "rank": 3, "label": "irrelevant", "reason": "fuel trader, no generators"}

Label every row of a request from rank 1 down (at least the first 10). Reason: under 15 words.

## The four labels

- `relevant` - the company makes or trades this exact product and could plausibly send a quotation for it.
  A distributor, dealer or trader of the right product is relevant. A maker is relevant even if no size is stated,
  as long as nothing says the requested size is outside its range.
- `partly` - the right product, but clearly the wrong specification: a maker of 20 kVA gensets for a 500 kVA
  request, seawater membranes for a brackish-water request. A different product is never "partly".
- `irrelevant` - anything else. In particular:
  - it only bought or used the product (a hospital, a utility, a ministry);
  - it only transports, stores, installs, repairs, rents or inspects it;
  - it works in the same sector without making or selling the product (a solar EPC for "solar panels" that sells
    no panels, a mill for "wheat" that sells only flour);
  - a look-alike: another product that shares a word (urea cream, coffee table, power cable ties, oil filters for "oil");
  - a consultant, contractor, NGO or bank.
- `cannot_tell` - the evidence and the website do not let you decide in about two minutes. Use it sparingly;
  it is left out of the precision figures.

## How to decide
1. Read the request as a buyer: what would have to arrive on site?
2. Read `evidence`. If it does not settle the question, open `website` (or search the company name with the
   product) and look for a product page. A company name alone proves nothing. Ignore rank and country.
3. One-word requests (`urea`, `generator`, `membrane`, `pipes`, `cable`, `oil`): any company that makes or trades a
   product a buyer could reasonably mean is relevant (fertilizer or technical urea; diesel or gas generator sets).
   Something that merely contains the word is irrelevant.

## Tender requests (ids starting with T)

The request is a tender title. First decide what the tender buys.

- It buys goods: label each supplier against those goods, as above.
- It buys no goods (works, services, consulting, a development programme, a study): every returned supplier is
  `irrelevant`, reason "no goods bought". The correct answer for such a tender is an empty list.
- Mixed (supply and installation, framework agreement, lots): relevant only for a company that supplies the goods part.
- If the stratum in `tenders.jsonl` is wrong, add one line with rank 0:
  `{"query_id": "T07", "rank": 0, "label": "non_goods", "reason": "road works"}`.

## Scoring (after labelling, on your own machine - the output names companies)
    python3 tools/eval_score.py rows.jsonl verdicts.jsonl labels.jsonl --tenders tenders.jsonl \
        --summary summary.json --human human_labels.jsonl
