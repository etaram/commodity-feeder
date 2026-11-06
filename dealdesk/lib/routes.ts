// Entry routes for one tender or project (skill: sinder-tender-route). One row per route, never a single verdict:
// a restriction on one route is not a blanket rejection, and an unverified partner is not a workaround.
//   direct        - Sinder (or the client) bids in its own name
//   agency        - a manufacturer bids or sells, Sinder earns a commission as its agent or representative
//   local_partner - a registered local company bids, Sinder supplies or co-bids through it
//   sub_supply    - Sinder supplies the main contractor (EPC, works contractor) after the award
// Verdicts: supported (the notice or our records allow it now), conditional (allowed if the listed conditions are met),
// blocked (an explicit clause excludes it), unknown (the facts that decide it are not in hand). Deterministic code;
// the clause text is quoted from the notice fields we hold, and a qualified reader decides material interpretations.
export type RouteId = "direct" | "agency" | "local_partner" | "sub_supply";
export type RouteVerdict = "supported" | "conditional" | "blocked" | "unknown";
export type RouteRow = { route: RouteId; verdict: RouteVerdict; basis: string; assumptions: string[]; missing: string[]; next: string };
export type RouteInput = {
  country: string;            // ISO3 of the buyer
  access?: string;            // access / eligibility wording from the notice ("international", "national bidders only", "GPA")
  title?: string; sector?: string; nature?: string; value_usd?: number | null;
  stage?: string;             // planned | tender | awarded | closed
  home?: string;              // the bidder's home country (ISR for Sinder)
  partner_countries?: string[];  // workspace strategy: countries where a partner relationship exists
  partner_state?: string;     // the deal's partner ladder state, if any (lib/deal.ts PARTNER_STATES)
  awarded_to?: string;        // main contractor, when an award is known
};

const OPEN = /\b(international|icb|global tender|gpa|open to (all|foreign)|foreign (bidders|firms|companies) (may|are eligible|can)|trade agreements?|eligible countries)\b/i;
const DOMESTIC = /\b(national (bidders|firms|companies|suppliers) only|local (bidders|firms|companies|suppliers) only|domestic (bidders|firms|suppliers|competition)|ncb|national competitive bidding|registered (in|with)[^.;]{0,40}(registry|register|chamber|ministry)|reserved for (local|national|domestic|sme|small)|nationals only|restricted to (local|national|domestic)|local content (of|at least|minimum))\b/i;
const WORKS = /\b(works?|construction|civil|epc|turnkey|design and build|installation|infrastructure|plant|rehabilitation|building)\b/i;

export function routeOptions(x: RouteInput): RouteRow[] {
  const acc = `${x.access || ""}`.trim();
  const home = (x.home || "ISR").toUpperCase(), cty = (x.country || "").toUpperCase();
  const isHome = !!cty && cty === home;
  const open = isHome || OPEN.test(acc), domestic = !isHome && DOMESTIC.test(acc);
  const quote = (rx: RegExp) => { const m = acc.match(rx); return m ? `"${acc.slice(Math.max(0, (m.index || 0) - 30), (m.index || 0) + m[0].length + 30).trim()}"` : ""; };
  const hasPartnerCountry = (x.partner_countries || []).map((c) => c.toUpperCase()).includes(cty);
  const ladder = x.partner_state || "";
  const works = WORKS.test(`${x.title || ""} ${x.sector || ""} ${x.nature || ""}`);
  const closed = /awarded|closed/i.test(x.stage || "");
  const rows: RouteRow[] = [];

  // direct
  if (closed) rows.push({ route: "direct", verdict: "blocked", basis: `notice is ${x.stage}: no open bid`, assumptions: [], missing: [], next: "Use the award to research the contractor's sub-supply needs." });
  else if (domestic) rows.push({ route: "direct", verdict: "blocked", basis: `eligibility wording ${quote(DOMESTIC)}`, assumptions: ["the clause applies to the bidder, not only to product origin"], missing: ["the full eligibility clause and any amendments"], next: "Have the clause read in the tender documents; if it binds the bidder, use a local partner or agency route." });
  else if (open) rows.push({ route: "direct", verdict: isHome ? "supported" : "conditional", basis: isHome ? "home market" : `access wording ${quote(OPEN)}`, assumptions: isHome ? [] : ["registration on the buyer's portal is open to foreign firms"], missing: isHome ? [] : ["portal registration requirements", "bid security form and local documents"], next: isHome ? "Check the eligibility documents and request supplier quotes." : "Confirm portal registration and bid-security rules for a foreign bidder, then request quotes." });
  else rows.push({ route: "direct", verdict: "unknown", basis: "the notice fields we hold do not state who may bid", assumptions: [], missing: ["eligibility clause (bidder nationality, registration, local content)"], next: "Read the eligibility section of the tender documents before any spend." });

  // agency
  if (closed) rows.push({ route: "agency", verdict: "unknown", basis: "no open bid; a manufacturer may still sell to the winner", assumptions: [], missing: ["the winner and its purchasing plan"], next: "Identify the winner and offer manufacturer representation for its supply packages." });
  else rows.push({ route: "agency", verdict: domestic ? "conditional" : "conditional", basis: domestic ? "a manufacturer registered or established locally may bid even when foreign bidders cannot" : "a manufacturer bids in its own name; Sinder earns a commission",
    assumptions: ["the manufacturer agrees in writing to a commission or representation agreement", domestic ? "the manufacturer qualifies as a local bidder" : "agents are permitted by the buyer's rules"],
    missing: ["a manufacturer willing to bid", "the buyer's rules on agents and commissions (disclosure, caps)"], next: "Shortlist manufacturers with supported product matches and ask whether they bid directly with a representative." });

  // local partner
  const lp: RouteRow = { route: "local_partner", verdict: "unknown", basis: "", assumptions: [], missing: [], next: "" };
  if (closed) Object.assign(lp, { verdict: "unknown", basis: "no open bid", next: "Keep the partner for the next notice from this buyer." });
  else if (ladder === "engagement confirmed") Object.assign(lp, { verdict: "supported", basis: "partner engagement confirmed with evidence (deal partner ladder)", assumptions: ["the partner is eligible under the clause"], missing: [], next: "Agree the split and the document responsibilities with the partner." });
  else if (ladder) Object.assign(lp, { verdict: "conditional", basis: `partner ladder: ${ladder}`, assumptions: ["the partner is eligible and willing"], missing: ["the next partner step's evidence (identity, capability, engagement)"], next: "Move the partner up the ladder: registry identity, then capability, then a written engagement." });
  else Object.assign(lp, { verdict: domestic ? "conditional" : hasPartnerCountry ? "conditional" : "unknown",
    basis: domestic ? "the domestic clause can be met by a registered local bidder" : hasPartnerCountry ? "the workspace has a partner relationship in this country (strategy)" : "no partner relationship on record for this country",
    assumptions: domestic || hasPartnerCountry ? ["a qualified local company agrees to bid and the split covers its costs"] : [],
    missing: ["an identified local partner with registry identity", "its capability for this scope"],
    next: domestic ? "Find a local distributor or contractor that already sells to this buyer; record it in the partner ladder." : "Only if the direct route is closed or weak: find a local partner candidate." });
  if (!closed) lp.assumptions.push("product origin rules are checked separately from bidder eligibility");
  rows.push(lp);

  // sub-supply to the main contractor
  if (x.awarded_to) rows.push({ route: "sub_supply", verdict: "conditional", basis: `awarded to ${x.awarded_to}`, assumptions: ["the contractor buys this scope from third parties"], missing: ["the contractor's procurement contact and package schedule"], next: `Offer the package to ${x.awarded_to}'s procurement team.` });
  else if (works || (x.value_usd || 0) >= 1_000_000) rows.push({ route: "sub_supply", verdict: "conditional", basis: works ? "works or EPC scope: the main contractor buys materials and equipment" : "large contract: the winner buys sub-packages", assumptions: ["the award is published and names the contractor"], missing: ["the award notice"], next: "Track the award; prepare the supply offer for the likely bidders now." });
  else rows.push({ route: "sub_supply", verdict: "unknown", basis: "small goods contract: little to sub-supply", assumptions: [], missing: [], next: "-" });
  return rows;
}

// Hebrew for the panel: a fixed dictionary, so the route text never depends on a model translation.
const HE: Record<string, string> = {
  "a manufacturer bids in its own name; Sinder earns a commission": "יצרן מגיש בשמו; Sinder מקבלת עמלה",
  "a manufacturer registered or established locally may bid even when foreign bidders cannot": "יצרן רשום או מבוסס מקומית רשאי להגיש גם כשמציעים זרים לא",
  "a manufacturer willing to bid": "יצרן שמוכן להגיש",
  "a qualified local company agrees to bid and the split covers its costs": "חברה מקומית כשירה מסכימה להגיש והחלוקה מכסה את עלויותיה",
  "agents are permitted by the buyer's rules": "כללי הקונה מתירים סוכנים",
  "an identified local partner with registry identity": "שותף מקומי מזוהה עם זהות ברשם",
  "bid security form and local documents": "נוסח ערבות ההצעה ומסמכים מקומיים",
  "eligibility clause (bidder nationality, registration, local content)": "סעיף הזכאות (אזרחות המציע, רישום, תוכן מקומי)",
  "home market": "שוק הבית",
  "its capability for this scope": "יכולתו בהיקף הזה",
  "large contract: the winner buys sub-packages": "חוזה גדול: הזוכה רוכש חבילות משנה",
  "no open bid": "אין הגשה פתוחה",
  "no open bid; a manufacturer may still sell to the winner": "אין הגשה פתוחה; יצרן עדיין יכול למכור לזוכה",
  "no partner relationship on record for this country": "אין קשר שותפות רשום במדינה הזו",
  "partner engagement confirmed with evidence (deal partner ladder)": "התקשרות עם השותף אושרה בראיה (סולם השותף בעסקה)",
  "portal registration requirements": "דרישות הרישום בפורטל",
  "product origin rules are checked separately from bidder eligibility": "כללי מקור המוצר נבדקים בנפרד מזכאות המציע",
  "registration on the buyer's portal is open to foreign firms": "הרישום בפורטל הקונה פתוח לחברות זרות",
  "small goods contract: little to sub-supply": "חוזה סחורה קטן: מעט לאספקת משנה",
  "the award is published and names the contractor": "הודעת הזכייה מתפרסמת ושמה את הקבלן",
  "the award notice": "הודעת הזכייה",
  "the buyer's rules on agents and commissions (disclosure, caps)": "כללי הקונה לגבי סוכנים ועמלות (גילוי, תקרות)",
  "the clause applies to the bidder, not only to product origin": "הסעיף חל על המציע ולא רק על מקור המוצר",
  "the contractor buys this scope from third parties": "הקבלן רוכש את ההיקף הזה מצדדים שלישיים",
  "the contractor's procurement contact and package schedule": "איש הרכש של הקבלן ולוח החבילות",
  "the domestic clause can be met by a registered local bidder": "מציע מקומי רשום יכול לעמוד בסעיף המקומי",
  "the full eligibility clause and any amendments": "סעיף הזכאות המלא וכל תיקון",
  "the manufacturer agrees in writing to a commission or representation agreement": "היצרן מסכים בכתב להסכם עמלה או ייצוג",
  "the manufacturer qualifies as a local bidder": "היצרן כשיר כמציע מקומי",
  "the next partner step's evidence (identity, capability, engagement)": "ראיה לשלב הבא של השותף (זהות, יכולת, התקשרות)",
  "the notice fields we hold do not state who may bid": "שדות ההודעה שבידינו לא מציינים מי רשאי להגיש",
  "the partner is eligible and willing": "השותף זכאי ומוכן",
  "the partner is eligible under the clause": "השותף זכאי לפי הסעיף",
  "the winner and its purchasing plan": "הזוכה ותוכנית הרכש שלו",
  "the workspace has a partner relationship in this country (strategy)": "לסביבת העבודה יש קשר שותפות במדינה (אסטרטגיה)",
  "works or EPC scope: the main contractor buys materials and equipment": "היקף עבודות או EPC: הקבלן הראשי רוכש חומרים וציוד",
  "Agree the split and the document responsibilities with the partner.": "לסכם עם השותף את החלוקה ואת האחריות למסמכים.",
  "Check the eligibility documents and request supplier quotes.": "לבדוק את מסמכי הזכאות ולבקש הצעות מספקים.",
  "Confirm portal registration and bid-security rules for a foreign bidder, then request quotes.": "לברר את הרישום בפורטל ואת כללי ערבות ההצעה למציע זר, ואז לבקש הצעות.",
  "Find a local distributor or contractor that already sells to this buyer; record it in the partner ladder.": "לאתר מפיץ או קבלן מקומי שכבר מוכר לקונה הזה ולרשום אותו בסולם השותף.",
  "Have the clause read in the tender documents; if it binds the bidder, use a local partner or agency route.": "לקרוא את הסעיף במסמכי המכרז; אם הוא מחייב את המציע, לעבור למסלול שותף מקומי או סוכנות.",
  "Identify the winner and offer manufacturer representation for its supply packages.": "לזהות את הזוכה ולהציע ייצוג יצרנים לחבילות האספקה שלו.",
  "Keep the partner for the next notice from this buyer.": "לשמור את השותף למכרז הבא של הקונה.",
  "Move the partner up the ladder: registry identity, then capability, then a written engagement.": "לקדם את השותף בסולם: זהות ברשם, יכולת, ואז התקשרות בכתב.",
  "Only if the direct route is closed or weak: find a local partner candidate.": "רק אם המסלול הישיר סגור או חלש: לאתר מועמד לשותף מקומי.",
  "Read the eligibility section of the tender documents before any spend.": "לקרוא את פרק הזכאות במסמכי המכרז לפני כל הוצאה.",
  "Shortlist manufacturers with supported product matches and ask whether they bid directly with a representative.": "לבחור יצרנים עם התאמת מוצר נתמכת ולשאול אם הם מגישים ישירות עם נציג.",
  "Track the award; prepare the supply offer for the likely bidders now.": "לעקוב אחרי הזכייה; להכין כבר עכשיו הצעת אספקה למציעים הסבירים.",
  "Use the award to research the contractor's sub-supply needs.": "להשתמש בזכייה כדי לחקור את צרכי אספקת המשנה של הקבלן.",
};
const he = (s: string) => HE[s] ?? s
  .replace(/^eligibility wording /, "נוסח הזכאות ").replace(/^access wording /, "נוסח הגישה ")
  .replace(/^notice is (.+): no open bid$/, "ההודעה במצב $1: אין הגשה פתוחה").replace(/^partner ladder: /, "סולם השותף: ")
  .replace(/^awarded to (.+)$/, "זכה: $1").replace(/^Offer the package to (.+)'s procurement team\.$/, "להציע את החבילה לצוות הרכש של $1.");
export function routesHe(rows: RouteRow[]): RouteRow[] {
  return rows.map((r) => ({ ...r, basis: he(r.basis), assumptions: r.assumptions.map(he), missing: r.missing.map(he), next: r.next === "-" ? "-" : he(r.next) }));
}
