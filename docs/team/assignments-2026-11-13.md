# Team assignments, 13 Nov 2026 afternoon (by Claude, per the owner's strategic plan)

Owner, 13 Nov 15:19: "manage them according to the strategic plan". Today = Layers 1-2 only (collection and
refinement), quality decides, no deals. Targets: 1,000,000 OPEN opportunities (future deadline) and 1,000,000
REFINED suppliers, 150+ countries, every segment, including large companies, municipalities, state infrastructure
companies, and (owner 12:08) private companies of medium size and up. Numbers are targets; only quality-passing
records count.

Where we stand (measured): 106,888 open / 178 countries (13:01, before Japan 1,497, Bonfire 249, Transnet 99,
TED full sweep and BidNet are published); 34,519 refined suppliers / 189 countries (gate 1.5).

The biggest gaps against the targets, in order of yield:
1. Large national markets not yet read: India GeM (~45k open, geo-blocked), Korea KONEPS (key pending), Indonesia,
   Turkey (EKAP v2), Vietnam and Mexico lists (CAPTCHA: official open data only).
2. US/Canada state and local (BidNet 25.6k, Bonfire hubs, bidsandtenders.ca, OpenGov).
3. Private companies' own procurement pages (scan of 85,473 company sites running).
4. Refined suppliers: the gate passes ~13% of the enrichment set; the main blockers are a missing role statement and
   a missing official contact, not missing websites any more.

## ChatGPT (evidence, rights, quality review; access team coordinator)
- A1 (due today 18:00): India/Singapore relay patch (sheet row 173) for my review; the owner types the secret.
- A2 (today): rights basis for BidNet Direct, Bonfire, KKJ, Transnet: allowed / needs consent / unknown, with the
  terms URL. Eskom stays paused until consent.
- A3 (today): review commit 2fc8fd5d and the next merge publication (snapshot -> index) evidence.
- A4 (access team): Korea KONEPS 7-day windows on BidPublicInfoService02 (ready for me to wire when the key exists);
  Turkey EKAP v2 public API route; Mexico open-data procedures file (not the CAPTCHA list).

## Gemini (Sources and Coverage Lead)
- G1 (today 20:00): for each of the 10 largest uncovered or under-covered markets (by public procurement volume),
  ONE official machine-readable route with: exact URL, a dated sample record with deadline, count of currently open
  notices, terms URL. Sheet Sources tab, new rows. No generic samples: a real notice id and deadline per row.
- G2: list of 200 real Bonfire / bidsandtenders.ca / OpenGov hub names (taken from the agencies' own websites) so
  the collectors stop guessing (only 23 of 194 guessed Bonfire hubs answered).
- G3 (after G1, G2): business development leads as agreed (private-company procurement portals: mining, oil and gas,
  utilities, EPC contractors) with the portal URL and whether the list is public.

## Grok (infrastructure sources only)
- K1 (today 20:00): the 22 utility sources added after row 68: for each, the exact list URL or JSON endpoint behind
  the page (as with Transnet /Home/GetAdvertisedTenders and Eskom /webapi/api/Lookup/GetTender), whether it is
  public without sign-in, and the terms clause on automated access. Sources tab Q-S for my test.
- K2: same for national power, water, port and rail companies of the 20 largest economies not yet covered.

## Claude (implementation, server, integration)
- Publish the collected Japan/Bonfire/Transnet/TED/BidNet rows; restart the procurement scan; 30-minute capacity
  checks until 23:00; wire every route the team hands over with tests; 15:00 hand sample; 20:00 evening report;
  23:00 release-gate report.
