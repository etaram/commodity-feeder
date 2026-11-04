# Deal Desk v2 design: decisions, tokens, route map

Source: upgrade brief section 9 (2026-11-04). Skill used: frontend-design (available in this environment). Not available
here: together-ai-design-skill, web-design-guidelines, vercel-react-best-practices, webapp-testing; their roles were done
directly (Playwright screenshots, contrast computation, keyboard focus styles).

## Switch
`?ui=classic` shows the previous interface and is remembered per browser; `?ui=v2` returns. Both read and write the same
records; nothing is migrated. Switch time: one page load.

## Tokens (light theme only for now)
| Token | Value | Use | Contrast |
|---|---|---|---|
| canvas `--bg` | #F5F7FA | workspace | |
| surface `--panel` | #FFFFFF | lists, detail, forms | |
| ink `--ink` | #172B4D | text, primary buttons, navigation | 14.1 on surface |
| muted `--muted` | #526175 | supporting text | 6.3 on surface, 5.9 on canvas |
| accent `--accent` | #8A6500 | selection, strong fits | 5.3 on surface |
| border `--line` | #CBD5E1 | separators only | 1.5 (decorative) |
| control `--ctl` | #7B8798 | input and button boundaries | 3.65 on surface |
| positive / warning / danger | #146C43 / #8A4B00 / #B42318 | statuses, always with words | 6.5 / 6.8 / 6.6 |
| navigation | #172B4D band, #C9A44A gold marker, #AEBBD0 labels | side nav / bottom bar | labels 7.3 |

Type: IBM Plex Sans and IBM Plex Sans Hebrew (already loaded, both scripts); Secular One only for the Sinder mark.
15 px body, 14.5 px rows, 13 px metadata, 20 px section titles, 24 px page titles, tabular figures.
Radius 7 px controls, 10 px panels. One soft elevation, on the floating detail panel only.
Score ring: each score is a ring filled to its value; gold for strong fits, never green (fit is not readiness).

## Navigation: five destinations, existing views as sub-tabs
| Destination | Sub-tabs (view ids, deep links #id unchanged) |
|---|---|
| Today / היום | today, forme (For me), intel (Intelligence) |
| Markets & Commodities / שווקים וסחורות | markets, deals (trade opportunities) |
| Global Projects / פרויקטים בעולם | tenders, grants |
| Suppliers & Buyers / ספקים וקונים | companies, research (Supplier research), contacts |
| My Deals / העסקאות שלי | desk (Deal Desk), projects (renamed "Bid projects" to separate private bids from global projects), jobs |
| Admin (secondary, admins only) | users |

Wide screens (1100 px and up): side navigation on the leading edge (right in Hebrew). Smaller: five-item bottom bar, admin
via a header button. The last sub-tab used in each destination is remembered.

## Checked (stub data, Playwright)
390, 768, 1280 and 1440 px, English and Hebrew: no page-wide horizontal scroll, no script errors; classic still shows all 14
tabs; a deep link (#companies) opens the right destination and sub-tab.

## Not done yet (next design slices)
Today as an action queue (decision, reason, deadline, owner, blocker, next step) with balanced commodity and project streams;
one global search with scope chips; tender detail as a guided sequence instead of equal-weight buttons; evidence drawer;
private deal workspace with quote comparison and compliance matrix; job states; keyboard and screen-reader walkthroughs on
the live site; timed tasks with real operators (pending people).
