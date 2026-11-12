#!/usr/bin/env python3
"""Benchmark F10: three classifiers on one task, TENDER KIND (what a tender buys: goods / non_goods / mixed).

  A. rules   dealdesk/lib/tenderkind.ts, scored by dealdesk/tools/eval-tenderkind.ts --jsonl=<file> (not run here)
  B. local   a small model served by Ollama on our own server           (subcommand: local)
  C. gemini  Google's Decisions API, model gemini-decision-1             (subcommand: gemini)
  report     joins the three with the labeller's strata and prints one table

Called by deploy/ops/bench-f10.sh. Every subcommand reads <data>/tenders.jsonl and <data>/labels.jsonl, which the
root step has already cut down to the TUNING ids; this file checks the ids again and refuses anything else.

THE WORKFLOW LOG IS PUBLIC. Nothing here prints a title, a sector or a model reply: only ids, counts and metrics.
Row-level answers go to <data>/detail.jsonl (ids, labels, confidence, latency; no titles), which the root step moves to
the server folder and to Google Drive.

The input is the same for all three: title, sector and procurement category of the tender, the three fields the
rule classifier is given. One fixed prompt per classifier, written before any result was seen; it is not to be tuned
on these 16 tenders.

Google: at most MAX_GOOGLE_REQUESTS requests over ALL runs of this benchmark. The count and the answers are kept in
<data>/gemini_state.json (stored on the server between runs), an answered tender is never asked again, there are no
retries, and the first refusal stops the phase. The key is read from the environment and sent only in the request
header. Standard library only.
"""
import argparse
import glob
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

TUNING_IDS = ("T02", "T03", "T05", "T07", "T09", "T10", "T11", "T12", "T13", "T14", "T18", "T19", "T21", "T23", "T24", "T27")
LABELS = ("goods", "non_goods", "mixed")

# ---- the fixed wording (same meaning for B and C; the definitions follow the labeller's guide in tools/eval_label.py) ----
DEFS = {
    "goods": "The tender buys physical products that a supplier can ship: equipment, materials, vehicles, medicines, food, fuel, spare parts.",
    "non_goods": "The tender buys no products: works, services, consulting, a study, training, or a development programme.",
    "mixed": "The tender buys products together with a real service or works part, for example supply and installation, or it has several lots or is a framework agreement covering both.",
}
SYSTEM = ("You classify a public tender by what it buys. The title can be in English, French, Spanish or Portuguese.\n"
          + "\n".join(f"{k}: {v}" for k, v in DEFS.items())
          + "\nAnswer with exactly one word: goods, non_goods or mixed.")
QUESTION = "What does this tender buy?"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/decisions"   # POST, header x-goog-api-key
GEMINI_MODEL = "gemini-decision-1"
GEMINI_USD_PER_M_INPUT = 0.10      # list price in the announcement of 11 Nov 2026; output tokens are free
MAX_GOOGLE_REQUESTS = 20           # over all runs of this benchmark


def say(s=""):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_tenders(data):
    """The tuning tenders, in id order. Any other id in the file is a fault of the fetch step: stop."""
    out, seen = [], set()
    for t in read_jsonl(os.path.join(data, "tenders.jsonl")):
        tid = str(t.get("query_id") or "")
        if tid not in TUNING_IDS:
            raise SystemExit("the tender file holds an id outside the tuning half: stopped")
        if tid in seen:
            continue
        seen.add(tid)
        out.append({"id": tid, "title": str(t.get("title") or ""), "sector": str(t.get("sector") or ""), "category": str(t.get("nature") or "")})
    return sorted(out, key=lambda t: t["id"])


def user_text(t):
    return f"Title: {t['title']}\nSector: {t['sector'] or '-'}\nProcurement category: {t['category'] or '-'}"


def load1():
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def parse_label(text):
    """One of the three labels from a model reply, or 'invalid'. A leaked thinking block is dropped first."""
    s = re.sub(r"<think>.*?</think>", " ", str(text or ""), flags=re.S).lower()
    m = re.search(r"non[\s_-]?goods|goods|mixed", s)
    if not m:
        return "invalid"
    return "non_goods" if m.group(0).startswith("non") else m.group(0)


def post_json(url, body, headers=None, timeout=180):
    """Returns (status, parsed JSON or None, seconds). Never raises for an HTTP error status."""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    dt = time.perf_counter() - t0
    try:
        return status, json.loads(raw.decode("utf-8")), dt
    except Exception:
        return status, None, dt


# ---------------------------------------------------------------- B. local model
def slug(model):
    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def cmd_local(a):
    tenders = load_tenders(a.data)
    host, model = a.host.rstrip("/"), a.model
    out = {"classifier": f"local {model}", "model": model, "items": [], "notes": []}
    for _ in range(60):      # the server inside the container needs a few seconds
        try:
            urllib.request.urlopen(host + "/api/tags", timeout=3).read()
            break
        except Exception:
            time.sleep(1)
    else:
        out["error"] = "the local model server did not answer"
        json.dump(out, open(os.path.join(a.data, f"local_{slug(model)}.json"), "w"))
        say(f"local {model}: the server did not answer")
        return 0
    try:
        with urllib.request.urlopen(host + "/api/version", timeout=5) as r:
            out["ollama_version"] = json.loads(r.read()).get("version")
    except Exception:
        pass

    def ask(messages, think_field=True):
        body = {"model": model, "messages": messages, "stream": False, "keep_alive": "10m", "options": {"temperature": 0, "num_predict": 16, "seed": 1}}
        if think_field:
            body["think"] = False
        return post_json(host + "/api/chat", body, timeout=300)

    # warm-up: loads the model into memory; not timed with the items and it shows no tender
    think_field = True
    status, _, dt = ask([{"role": "user", "content": "Say ok."}])
    if status == 400:        # an older server or a model without a thinking switch: same prompt, switch written in the text
        think_field = False
        out["notes"].append("server refused the think field; /no_think written in the prompt instead")
        status, _, dt = ask([{"role": "user", "content": "Say ok. /no_think"}], False)
    out["load_seconds"] = round(dt, 1)
    if status != 200:
        out["error"] = f"warm-up failed with HTTP {status}"
        json.dump(out, open(os.path.join(a.data, f"local_{slug(model)}.json"), "w"))
        say(f"local {model}: warm-up failed with HTTP {status}")
        return 0
    peak_load = load1() or 0.0
    for t in tenders:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_text(t) + ("" if think_field else " /no_think")}]
        try:
            status, js, dt = ask(msgs, think_field)
        except Exception as e:      # a timeout or a dropped connection
            out["items"].append({"id": t["id"], "answer": "error", "ms": None, "error": type(e).__name__})
            continue
        ans = parse_label(((js or {}).get("message") or {}).get("content")) if status == 200 else "error"
        item = {"id": t["id"], "answer": ans, "ms": round(dt * 1000, 1)}
        if status != 200:
            item["error"] = f"HTTP {status}"
        if js:
            item["prompt_tokens"], item["output_tokens"] = js.get("prompt_eval_count"), js.get("eval_count")
        out["items"].append(item)
        peak_load = max(peak_load, load1() or 0.0)
    out["host_load1_peak"] = round(peak_load, 2)
    out["host_cpus"] = os.cpu_count()
    json.dump(out, open(os.path.join(a.data, f"local_{slug(model)}.json"), "w"))
    say(f"local {model}: {sum(1 for i in out['items'] if i['answer'] in LABELS)} of {len(tenders)} answered with one of the three labels; model load {out['load_seconds']} s")
    return 0


# ---------------------------------------------------------------- C. Gemini Decisions API
def gemini_error(js, status, key, hide):
    """What may be shown about a refusal: HTTP status, Google's error status and reason. The message is scrubbed."""
    err = (js or {}).get("error") if isinstance(js, dict) else None
    err = err if isinstance(err, dict) else {}
    reasons = [str(d.get("reason")) for d in (err.get("details") or []) if isinstance(d, dict) and d.get("reason")]
    msg = str(err.get("message") or "")
    for h in [key] + list(hide):
        if h and len(h) > 3:
            msg = msg.replace(h, "[hidden]")
    return {"http_status": status, "error_status": str(err.get("status") or ""), "reasons": reasons, "message": msg[:200]}


def cmd_gemini(a):
    tenders = load_tenders(a.data)
    spath = os.path.join(a.data, "gemini_state.json")
    state = json.load(open(spath)) if os.path.exists(spath) else {}
    state.setdefault("requests_sent", 0)
    state.setdefault("answers", {})
    state.pop("stopped", None)
    key = os.environ.get("GEMINI_API_KEY", "").strip()

    def save():
        json.dump(state, open(spath, "w"))

    if not key:
        state["stopped"] = {"reason": "secret_missing", "detail": "GEMINI_API_KEY is empty in the workflow environment (the repository secret is missing or not passed)"}
        save()
        say(f"gemini: not measured - the secret GEMINI_API_KEY is not in the environment; requests sent to Google so far: {state['requests_sent']}")
        return 0
    criteria = dict(DEFS)
    for t in tenders:
        if t["id"] in state["answers"]:
            continue
        if state["requests_sent"] >= MAX_GOOGLE_REQUESTS:
            state["stopped"] = {"reason": "request_budget", "detail": f"the ceiling of {MAX_GOOGLE_REQUESTS} requests to Google is used up"}
            break
        body = {"model": GEMINI_MODEL, "input": user_text(t), "questions": {"kind": {"type": "choice", "instructions": QUESTION, "criteria": criteria}}}
        state["requests_sent"] += 1
        save()                      # counted before it is sent: a crash can never make the count too low
        try:
            status, js, dt = post_json(GEMINI_URL, body, {"x-goog-api-key": key}, timeout=60)
        except Exception as e:
            state["stopped"] = {"reason": "network", "detail": type(e).__name__, "at": t["id"]}
            break
        if status != 200:
            state["stopped"] = {"reason": "api_refused", "at": t["id"], **gemini_error(js, status, key, [t["title"], t["sector"]])}
            break
        ans = (js or {}).get("answers")
        one = ans.get("kind") if isinstance(ans, dict) else next((x for x in ans if isinstance(x, dict)), None) if isinstance(ans, list) else None
        if not isinstance(one, dict) or one.get("choice") not in LABELS:
            shape = sorted(js.keys()) if isinstance(js, dict) else type(js).__name__
            inner = sorted(one.keys()) if isinstance(one, dict) else type(one).__name__
            state["stopped"] = {"reason": "unexpected_response", "at": t["id"], "top_level_keys": shape, "answer_keys": inner}
            break
        usage = js.get("usage") if isinstance(js.get("usage"), dict) else {}
        state["answers"][t["id"]] = {"answer": one["choice"], "confidence": one.get("confidence"), "probabilities": one.get("probabilities"),
                                     "ms": round(dt * 1000, 1), "input_tokens": usage.get("total_input_tokens", usage.get("input_tokens"))}
        save()
    save()
    got = sum(1 for t in tenders if t["id"] in state["answers"])
    say(f"gemini: answers for {got} of {len(tenders)} tuning tenders; requests sent to Google over all runs: {state['requests_sent']} (ceiling {MAX_GOOGLE_REQUESTS})")
    st = state.get("stopped")
    if st:
        shown = {k: st[k] for k in ("reason", "at", "http_status", "error_status", "reasons", "message", "detail", "top_level_keys", "answer_keys") if k in st}
        say("gemini: stopped - " + json.dumps(shown, ensure_ascii=True))
    return 0


# ---------------------------------------------------------------- report
def pctl(xs, q):
    """Nearest-rank percentile."""
    xs = sorted(xs)
    return xs[max(0, math.ceil(q * len(xs)) - 1)] if xs else None


def fmt_ms(x):
    return "n/a" if x is None else (f"{x:.3f}" if x < 1 else f"{x:.0f}")


def fmt_mem(b):
    return "n/a" if not b else (f"{b / 2**30:.2f} GB" if b >= 2**30 else f"{b / 2**20:.0f} MB")


def cmd_report(a):
    tenders = load_tenders(a.data)
    ids = [t["id"] for t in tenders]
    truth = {}
    for r in read_jsonl(os.path.join(a.data, "labels.jsonl")):
        lab = str(r.get("label") or "").strip().lower().replace(" ", "_")
        qid = str(r.get("query_id") or "").strip()
        if qid in TUNING_IDS and int(r.get("rank") or 0) == 0 and lab in LABELS:
            truth[qid] = lab
    scored = [i for i in ids if i in truth]
    cols = []    # (name, {id: {answer, confidence, ms}}, peak RAM text, cost for the answered ids or None, notes)

    rules, rss = {}, None
    rp = os.path.join(a.data, "rules.jsonl")
    if os.path.exists(rp):
        for r in read_jsonl(rp):
            if r.get("id") == "_process":
                rss = r.get("rss_bytes")
            elif r.get("id") in TUNING_IDS:
                rules[r["id"]] = {"answer": r.get("kind"), "confidence": r.get("confidence"), "ms": r.get("ms")}
    unk = sum(1 for v in rules.values() if v["answer"] == "unknown")
    cols.append(("A rules", rules, fmt_mem(rss) + " (whole node process)", 0.0,
                 "code, no model" + (f"; answered 'unknown' for {unk} (counted as wrong)" if unk else "") + ("" if rules else "; NOT MEASURED: the rules step wrote no answers")))

    for p in sorted(glob.glob(os.path.join(a.data, "local_*.json"))):
        d = json.load(open(p))
        mem = None
        try:
            mem = int(open(p[:-5] + ".mem").read().strip())
        except Exception:
            pass
        notes = [f"own server, container 3 CPUs / 6 GB; load time {d.get('load_seconds', 'n/a')} s (not in the latency); host 1-min load peak {d.get('host_load1_peak', 'n/a')} on {d.get('host_cpus', '?')} CPUs"]
        notes += d.get("notes") or []
        if d.get("error"):
            notes.append("NOT MEASURED: " + d["error"])
        bad = sum(1 for i in d.get("items", []) if i["answer"] not in LABELS)
        if bad:
            notes.append(f"{bad} replies were not one of the three labels (counted as wrong)")
        cols.append((f"B {d.get('classifier', 'local')}", {i["id"]: i for i in d.get("items", [])}, fmt_mem(mem) + " (container peak)", 0.0, "; ".join(notes)))
    for p in sorted(glob.glob(os.path.join(a.data, "local_*.skipped"))):
        cols.append((f"B local {open(p).readline().strip()}", {}, "n/a", None, "NOT MEASURED: " + (open(p).read().split("\n", 1) + [""])[1].strip()))

    gs = {}
    gp = os.path.join(a.data, "gemini_state.json")
    if os.path.exists(gp):
        gs = json.load(open(gp))
    gans = {k: v for k, v in (gs.get("answers") or {}).items() if k in TUNING_IDS}
    toks = [v.get("input_tokens") for v in gans.values() if isinstance(v.get("input_tokens"), (int, float))]
    gcost = sum(toks) * GEMINI_USD_PER_M_INPUT / 1e6 if toks and len(toks) == len(gans) else None
    st = gs.get("stopped") or {}
    gnote = f"{GEMINI_MODEL}; requests sent to Google over all runs {gs.get('requests_sent', 0)} of {MAX_GOOGLE_REQUESTS} allowed"
    if toks:
        gnote += f"; input tokens {sum(toks)} for {len(toks)} tenders; list price ${GEMINI_USD_PER_M_INPUT}/1M input tokens, the free tier charged 0"
    if st:
        why = st.get("reason", "")
        if "http_status" in st:
            why += f" HTTP {st['http_status']} {st.get('error_status', '')} {' '.join(st.get('reasons') or [])}".rstrip()
        gnote += f"; {'NOT MEASURED' if not gans else 'INCOMPLETE'}: {why}"
    cols.append(("C gemini decisions", gans, "n/a (Google's servers)", gcost, gnote))

    n = len(scored)
    n_goods = sum(1 for i in scored if truth[i] == "goods")
    n_ng = sum(1 for i in scored if truth[i] == "non_goods")
    n_mixed = sum(1 for i in scored if truth[i] == "mixed")
    say("")
    say(f"BENCHMARK F10 - tender kind, tuning half only: {len(ids)} tenders, {n} with a label (goods {n_goods}, non_goods {n_ng}, mixed {n_mixed}). SMALL SAMPLE: read the counts, not percentages.")
    say("cost formula: cost for 16 = sum of billed input tokens x list price per token; per 1,000 tenders = cost for 16 / tenders answered x 1,000. Rules and the local model make no paid call (server time and electricity are not priced).")
    say("latency: wall clock per tender; p95 by nearest rank, which with 16 values is the slowest one.")
    say("")
    head = ["classifier", f"correct of {n}", f"goods called non_goods (of {n_goods} goods)", f"non_goods caught of {n_ng}", "median ms", "p95 ms", "peak RAM", "cost USD for 16", "USD per 1,000", "notes"]
    say("| " + " | ".join(head) + " |")
    say("|" + "|".join(["---"] * len(head)) + "|")
    wrong_lines, summary = [], {"ids": ids, "labelled": n, "strata": {"goods": n_goods, "non_goods": n_ng, "mixed": n_mixed}, "classifiers": []}
    for name, ans, mem, cost, notes in cols:
        have = [i for i in scored if i in ans]
        correct = sum(1 for i in have if ans[i]["answer"] == truth[i])
        costly = sum(1 for i in have if truth[i] == "goods" and ans[i]["answer"] == "non_goods")
        caught = sum(1 for i in have if truth[i] == "non_goods" and ans[i]["answer"] == "non_goods")
        ms = [ans[i]["ms"] for i in ids if i in ans and isinstance(ans[i].get("ms"), (int, float))]
        med, p95 = (statistics.median(ms) if ms else None), pctl(ms, 0.95)
        if not have:
            row = [name, "not measured", "not measured", "not measured", "n/a", "n/a", mem, "n/a", "n/a", notes]
        else:
            part = "" if len(have) == n else f" (answered {len(have)})"
            c16 = "n/a" if cost is None else ("0" if cost == 0 else f"{cost:.6f}")
            c1k = "n/a" if cost is None else ("0" if cost == 0 else f"{cost / len(ans) * 1000:.4f}")
            row = [name, f"{correct} of {n}{part}", f"{costly} of {n_goods}", f"{caught} of {n_ng}", fmt_ms(med), fmt_ms(p95), mem, c16, c1k, notes]
        say("| " + " | ".join(str(x) for x in row) + " |")
        wrong = [i for i in scored if i in ans and ans[i]["answer"] != truth[i]]
        missing = [i for i in scored if i not in ans]
        wrong_lines.append(f"{name}: wrong {' '.join(wrong) or '-'}" + (f"; no answer {' '.join(missing)}" if missing and have else "") + ("" if have else " (not measured)"))
        summary["classifiers"].append({"name": name, "answered": len(have), "correct": correct, "goods_called_non_goods": costly, "non_goods_caught": caught,
                                       "median_ms": med, "p95_ms": p95, "peak_ram": mem, "cost_usd_16": cost, "wrong_ids": wrong, "notes": notes})
    say("")
    say("tuning ids each classifier got wrong (ids only):")
    for line in wrong_lines:
        say("  " + line)
    if gs.get("stopped"):
        summary["gemini_stopped"] = gs["stopped"]
    with open(os.path.join(a.data, "detail.jsonl"), "w", encoding="utf-8") as f:
        for i in ids:
            row = {"id": i, "truth": truth.get(i, "no_label")}
            for name, ans, *_ in cols:
                v = ans.get(i)
                row[name] = None if v is None else {k: v.get(k) for k in ("answer", "confidence", "probabilities", "ms") if v.get(k) is not None}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary["prompt"] = {"system": SYSTEM, "question": QUESTION, "criteria": DEFS, "input": "Title / Sector / Procurement category"}
    json.dump(summary, open(os.path.join(a.data, "summary.json"), "w"), indent=1)
    say(f"detail written: detail.jsonl ({len(ids)} lines: truth, each classifier's answer, confidence, latency; no titles) and summary.json")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("local", "gemini", "report"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True)
        if name == "local":
            p.add_argument("--model", required=True)
            p.add_argument("--host", default="http://127.0.0.1:11434")
    a = ap.parse_args(argv)
    try:
        return {"local": cmd_local, "gemini": cmd_gemini, "report": cmd_report}[a.cmd](a)
    except SystemExit:
        raise
    except Exception as e:      # the log is public: the kind of fault and where, never its text
        tb = e.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        say(f"{a.cmd}: failed with {type(e).__name__} at line {tb.tb_lineno}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
