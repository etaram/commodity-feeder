// The scouts' chooser (lib/scout.ts): limits, idempotency, the focus filter, who is assigned, and reasons that can be
// read back from the signal's own fields. Pure: no sheet, no network, no model. All names are made up.
import { ageDays, assign, cellsToSeen, choose, focusHits, LIMIT, NO_FOCUS, PURSUED, pursuedOn, regionMember, scoreSignal, seenToCells, START_FAILED, transient, winnerSignalId,
  type Focus, type Limits, type SeenRow, type Signal } from "@/lib/scout";
import { TEAM } from "@/lib/team";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

const NOW = Date.parse("2026-11-12T08:00:00Z");
const LIM: Limits = { maxRunsPerDay: 3, runsToday: 0, maxRunsPerRound: 3, budgetRuns: Infinity, minScore: 40, look: 12, maxTurns: 12, winnerDays: 21, minDaysLeft: 10 };
const winner = (o: Partial<Signal> = {}): Signal => ({ kind: "winner", id: "W1", title: "Supply of white maize, 5,000 t", country: "KEN", buyer: "Example Grain Board", value_usd: 4_000_000, date: "2026-11-09",
  winner: "Acme Trading Ltd", winner_country: "KEN", winner_kind: "commodity", needs: ["maize"], commodity: "maize", website: "https://acme.example", contact: "sales@acme.example", ...o });
const tender = (o: Partial<Signal> = {}): Signal => ({ kind: "tender", id: "T1", title: "Supply of distribution transformers", country: "IND", buyer: "Example Utility", value_usd: 12_000_000, days_left: 30, fit: 80,
  sector: "Power & electrical equipment", access: "International competitive bidding", decision: "Pursue", commodity: "transformers", buyer_awards: 4, ...o });
const seen = (o: Partial<SeenRow>): SeenRow => ({ time: "2026-11-12T06:10:00.000Z", ws: "sinder", kind: "winner", id: "W1", score: 60, decision: PURSUED, run_id: "AG1", assignees: ["relations_africa"], label: "x", reasons: [], deal_id: "", ...o });

// ---- score and reasons
const sw = scoreSignal(winner(), NO_FOCUS, NOW, LIM);
ok(sw.skip === "" && sw.score === 10 + 27 + 5 + 10 && sw.reasons.some((r) => /awarded 3 days ago \(2026-11-09\): \+27/.test(r)) && sw.reasons.some((r) => /value USD 4\.0M: \+10/.test(r)), "a winner's score is the sum of its named points (value, recency, commodity, contact)");
ok(sw.reasons.every((r) => /[+]\d+|: \+0/.test(r)) && sw.reasons.some((r) => /published commercial contact on record: \+10/.test(r)), "every reason carries its points and names the field it came from");
ok(scoreSignal(winner({ winner_country: "TUR" }), NO_FOCUS, NOW, LIM).score === sw.score + 10, "a foreign winner adds 10 points, with the two countries in the reason");
ok(scoreSignal(winner({ buyer_awards: 12 }), NO_FOCUS, NOW, LIM).score === sw.score + 5 && scoreSignal(winner({ buyer_awards: 1 }), NO_FOCUS, NOW, LIM).score === sw.score, "the buyer's award record counts only when it is known and large enough");
ok(scoreSignal(winner({ date: "2026-10-01" }), NO_FOCUS, NOW, LIM).skip === "skipped: not fresh" && scoreSignal(winner({ date: "" }), NO_FOCUS, NOW, LIM).skip === "skipped: no date", "an old award, or one with no date, is not a fresh signal");
const st = scoreSignal(tender(), NO_FOCUS, NOW, LIM);
ok(st.skip === "" && st.score === 16 + 10 + 24 + 10 + 10 + 10 + 5 + 5 && st.reasons.some((r) => /system deal fit 80: \+24/.test(r)) && st.reasons.some((r) => /names a commodity \(transformers\)/.test(r)), "a tender's score: value, new, fit, deadline, goods, access, decision, buyer record");
ok(scoreSignal(tender({ days_left: 4 }), NO_FOCUS, NOW, LIM).skip === "skipped: deadline too close" && scoreSignal(tender({ access: "reserved for local bidders (set-aside)" }), NO_FOCUS, NOW, LIM).skip === "skipped: reserved for local bidders", "a tender closing too soon or reserved for locals is skipped with the reason");
ok(scoreSignal(tender({ commodity: "", nature: "Goods" }), NO_FOCUS, NOW, LIM).reasons.some((r) => /nature of the tender is goods/.test(r)) && scoreSignal(tender({ commodity: "" }), NO_FOCUS, NOW, LIM).reasons.some((r) => /no goods marker/.test(r)), "the goods point uses the nature field when a row has one, and says so when there is no marker");
ok(Number.isNaN(ageDays("soon", NOW)) && ageDays("2026-11-12", NOW) === 0 && Number.isNaN(ageDays("2027-01-01", NOW)), "an unreadable or future date has no age");

// ---- focus
const F: Focus = { words: ["transformers", "solar"], partners: ["IND"], excluded: ["RUS"] };
ok(focusHits(tender(), F).join() === "transformers" && scoreSignal(tender(), F, NOW, LIM).score === Math.min(100, st.score + 25), "a focus word in the title adds 20 and a partner country 5");
ok(scoreSignal(winner(), F, NOW, LIM).skip === "skipped: outside focus" && scoreSignal(tender({ country: "RUS" }), F, NOW, LIM).skip === "skipped: excluded country", "with a focus set, a signal outside it or in an excluded country is skipped");
const cf = choose([winner(), tender()], [], "sinder", F, LIM, NOW);
ok(cf.chosen.length === 1 && cf.chosen[0].signal.id === "T1" && cf.skipped.length === 1 && cf.skipped[0].decision === "skipped: outside focus", "the focus filter leaves only the fitting signal; the other is recorded as outside focus");
ok(choose([winner(), tender()], [], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 2, "an empty focus filters nothing");

// ---- assignment
ok(assign(winner()).lead.id === "relations_africa" && assign(winner()).support.map((m) => m.id).join() === "analyst", "a winner in Kenya goes to the Africa relations member, with the tender analyst reading the contract");
ok(assign(winner({ winner_country: "TUR", country: "KEN" })).lead.id === "relations_europe" && /winner country TUR/.test(assign(winner({ winner_country: "TUR" })).why), "the region is the winner's own country when the award states it");
ok(assign(winner({ winner_country: "", country: "BRA" })).lead.id === "relations_latam" && /project country BRA/.test(assign(winner({ winner_country: "", country: "BRA" })).why), "otherwise the project country decides, and the reason says so");
ok(assign(winner({ winner_country: "", country: "" })).lead.id === "analyst" && assign(tender()).lead.id === "analyst" && assign(tender()).support[0].id === "sourcing", "a tender, or an award with no country, is led by the analyst");
ok(regionMember("VNM")?.id === "relations_asia" && regionMember("IND")?.id === "relations_south_asia" && regionMember("EGY")?.id === "relations_mena" && regionMember("XXX") === null, "countries map to the regional members of the roster");
const everyone = new Set(TEAM.map((m) => m.id));
ok(["KEN", "CHN", "IND", "BRA", "DEU", "ARE", "USA", "", "ZZZ"].every((c) => { const a = assign(winner({ winner_country: c, country: c })); return everyone.has(a.lead.id) && a.support.every((m) => everyone.has(m.id)); }), "only members of the roster are ever assigned");

// ---- limits
const many = [1, 2, 3, 4, 5].map((n) => winner({ id: `W${n}`, value_usd: n * 20_000_000 }));
const c3 = choose(many, [], "sinder", NO_FOCUS, LIM, NOW);
ok(c3.chosen.length === 3 && c3.skipped.length === 2 && c3.skipped.every((p) => p.decision === LIMIT && /daily run limit/.test(p.reasons[0])), "no more runs than the daily limit; the rest are held with the limit as the reason");
ok(c3.chosen.every((p, i, a) => i === 0 || a[i - 1].score >= p.score), "the best scores are taken first");
ok(choose(many, [], "sinder", NO_FOCUS, { ...LIM, runsToday: 3 }, NOW).chosen.length === 0 && choose(many, [], "sinder", NO_FOCUS, { ...LIM, runsToday: 2 }, NOW).chosen.length === 1, "runs already started today count against the limit");
const cb = choose(many, [], "sinder", NO_FOCUS, { ...LIM, budgetRuns: 0 }, NOW);
ok(cb.chosen.length === 0 && /AI budget/.test(cb.held_by) && cb.skipped.every((p) => p.decision === LIMIT), "no room in the AI budget: nothing is chosen");
ok(choose(many, [], "sinder", NO_FOCUS, { ...LIM, maxRunsPerRound: 1 }, NOW).chosen.length === 1, "one round starts no more than its own limit");
const low = choose([winner({ value_usd: 0, date: "2026-10-25", winner_kind: "contractor", contact: "", website: "" })], [], "sinder", NO_FOCUS, LIM, NOW);
ok(low.chosen.length === 0 && low.skipped[0].decision === "skipped: low score" && /under the minimum 40/.test(low.skipped[0].reasons[0]), "a signal under the minimum score is skipped, not started");
ok(choose(many, [], "sinder", NO_FOCUS, { ...LIM, look: 2 }, NOW).chosen.length === 2, "a round looks at a bounded number of signals");

// ---- idempotency
ok(choose([winner()], [seen({})], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 0, "a signal already pursued is never chosen again");
ok(choose([winner()], [seen({ decision: "skipped: outside focus", run_id: "" })], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 0, "a signal turned down for good is not looked at again");
ok(choose([winner()], [seen({ decision: LIMIT, run_id: "" })], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 1 && choose([winner()], [seen({}), seen({ decision: START_FAILED, run_id: "" })], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 1, "a signal held by a limit, or whose run failed to start, may be taken later");
ok(transient(LIMIT) && transient(START_FAILED) && !transient(PURSUED) && !transient("skipped: low score"), "only the limit and a failed start are passing decisions");
ok(choose([winner()], [seen({ ws: "acme" })], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 1, "another workspace's record does not hide a signal");
ok(choose([winner(), winner()], [], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 1 && choose([winner({ id: "" })], [], "sinder", NO_FOCUS, LIM, NOW).chosen.length === 0, "the same signal twice in the data is one signal; a signal without an id is ignored");
ok(pursuedOn([seen({}), seen({ run_id: "" }), seen({ id: "W2", time: "2026-11-11T06:00:00.000Z" }), seen({ id: "W3", decision: LIMIT })], "sinder", "2026-11-12") === 1, "runs started today are counted once per signal, from the pursued rows of that day");
ok(winnerSignalId({ id: "A-77" }) === "A-77" && winnerSignalId({ w: ["Acme Trading Ltd"], t: "Supply of maize", d: "2026-11-09" }) === winnerSignalId({ w: ["ACME  Trading, Ltd"], t: "supply of maize", d: "2026-11-09" }), "a winner without an index id gets a stable id from its name, title and date");

// ---- brief and storage
const pw = choose([winner()], [], "sinder", NO_FOCUS, LIM, NOW).chosen[0], pt = choose([tender()], [], "sinder", NO_FOCUS, LIM, NOW).chosen[0];
ok(/^Scout lead, contract winner: Acme Trading Ltd won "Supply of white maize/.test(pw.brief) && /inferred from the contract title, not confirmed/.test(pw.brief) && /propose_message a short first note/.test(pw.brief) && /Grace Mwangi/.test(pw.brief), "the winner brief: confirm, infer and say it is inferred, match suppliers, propose a first note by the assigned member");
ok(/tender_routes on T1/.test(pt.brief) && /eligibility/.test(pt.brief) && /deal_economics/.test(pt.brief) && /request for quotation/.test(pt.brief), "the tender brief: route, eligibility, goods, shortlist, economics outline, an RFQ proposal");
ok([pw, pt].every((p) => /Do not use ask_owner/.test(p.brief) && /at most 12 steps/.test(p.brief) && /why it is worth his time/.test(p.brief) && /Nothing is sent by you/.test(p.brief) && p.brief.length < 4000), "both briefs: no question to the owner, the step limit, the final report, nothing is sent");
const row = seen({ reasons: ["value USD 4.0M: +10", "awarded 3 days ago: +27"], label: "Acme Trading Ltd: Supply", assignees: ["relations_africa", "analyst"], deal_id: "AGENT-AG1" });
const back = cellsToSeen(seenToCells(row).map(String));
ok(!!back && back.decision === PURSUED && back.reasons.length === 2 && back.assignees.join() === "relations_africa,analyst" && back.deal_id === "AGENT-AG1" && back.score === 60, "a decision row survives the sheet: columns time, workspace, kind, id, score, decision, run id and the rest");
ok(cellsToSeen(["#"]) === null && cellsToSeen(["t", "sinder", "other", "x"]) === null, "the marker row and unknown kinds are not decisions");

if (fail) { console.log(`${fail} failed`); process.exit(1); }
