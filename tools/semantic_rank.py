#!/usr/bin/env python3
"""Semantic matching on our own CPU server: open-source models through ONNX (fastembed), no hosted API, no fee.

Runs inside a python:3.12-slim container at low priority (at most 3.5 CPUs, CPU shares 128, nice 19, 6 GB; started by
deploy/ops/_semantic_root.sh), so it uses idle capacity and yields to the database, gateway and website. The
packages live in a virtual environment on the server (fastembed, numpy, cryptography); the model files are cached on
the server after the first download.

Subcommands
  universe  decrypts the supplier index the app reads (data/web/suppliers.enc, key WEB_INDEX_KEY from the environment)
            and writes one line per supplier: row number, the app's dedupe key, and the text the models read
  bench     one model on the TUNING half of the frozen evaluation: scores every labelled row of every tuning request
            against its request text, measures load time, memory and throughput; writes scores_<slug>.jsonl and
            speed_<slug>.json into the work folder
  report    joins the scores with the blind labels: relevant-in-top-10 per stratum for the baseline order (rows.jsonl),
            each embedding model and each reranker; prints counts only; writes summary.json and detail.jsonl
  embed     embeds the whole supplier universe into float16 vectors, in resumable parts (progress counts only)
  serve     a tiny HTTP service on the docker network: GET /search?q=<text>&n=<count> returns the top supplier ids

THE WORKFLOW LOG IS PUBLIC. Nothing here prints a request text, a supplier name or any evidence text: only ids,
counts, timings and metrics. Row-level scores go to files that stay on the server (root only) and on Google Drive.

The method of the bench is fixed before any result is seen: the request text is the "query" field of rows.jsonl; the
supplier text is the "evidence" field (what the matcher read: products, industries, site title, what it supplied,
customs headings, commodity tags, HS codes), or the supplier name when the evidence is empty. Only rows that carry a
label are re-ordered, so every row in a re-ordered top 10 has a label. Ties keep the original rank order.
"""
import argparse
import gzip
import hashlib
import http.server
import json
import os
import re
import resource
import sys
import time
import traceback
import urllib.parse

TUNING_IDS = ("Q05 Q06 Q07 Q08 Q09 Q13 Q14 Q15 Q19 Q20 Q24 Q25 Q26 Q27 Q30 Q31 Q33 Q34 Q35 Q37 Q39 Q40 "
              "T02 T03 T05 T07 T09 T10 T11 T12 T13 T14 T18 T19 T21 T23 T24 T27").split()
LABELS = ("relevant", "partly", "irrelevant", "cannot_tell")
STRATA = ("product", "goods", "non_goods", "mixed")
THREADS = int(os.environ.get("SEM_THREADS", "3"))

# Qwen3 embeddings expect an instruction in front of the query and nothing in front of a document.
QWEN_TASK = "Given a buyer's request for a product, or a public tender title, retrieve companies that make or sell what is bought"

# name -> how to load it. "lic" is the licence on the model card (checked by hand; all allow commercial use).
EMBEDDERS = {
    "multilingual-e5-small": {"lic": "MIT", "dim": 384, "q": "query: ", "d": "passage: ", "pool": "mean",
                              "src": ["intfloat/multilingual-e5-small", "Xenova/multilingual-e5-small"], "file": "onnx/model.onnx"},
    "multilingual-e5-base": {"lic": "MIT", "dim": 768, "q": "query: ", "d": "passage: ", "pool": "mean",
                             "src": ["intfloat/multilingual-e5-base", "Xenova/multilingual-e5-base"], "file": "onnx/model.onnx"},
    "paraphrase-multilingual-MiniLM-L12-v2": {"lic": "Apache-2.0", "dim": 384, "q": "", "d": "",
                                              "builtin": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"},
    "Qwen3-Embedding-0.6B-int8": {"lic": "Apache-2.0", "dim": 1024, "q": f"Instruct: {QWEN_TASK}\nQuery:", "d": "",
                                  "builtin": "Qwen/Qwen3-Embedding-0.6B-Q"},
}
RERANKERS = {
    "bge-reranker-v2-m3-int8": {"lic": "Apache-2.0", "builtin": "BAAI/bge-reranker-v2-m3-int8"},
    "bge-reranker-v2-m3": {"lic": "Apache-2.0", "builtin": "BAAI/bge-reranker-v2-m3"},
}


def say(s=""):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def peak_rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def cgroup_peak_mb():
    for p in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"):
        try:
            return round(int(open(p).read().strip()) / 2**20)
        except (OSError, ValueError):
            continue
    return None


def dir_bytes(path):
    """Size of the files a model download left in the cache (hub layout: real files under blobs/, links elsewhere)."""
    n = 0
    for root, _, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            if not os.path.islink(p):
                n += os.path.getsize(p)
    return n


def cache_size_for(cache, repos):
    total = 0
    for name in os.listdir(cache) if os.path.isdir(cache) else []:
        if any(name.endswith(r.replace("/", "--")) or name.endswith(r.split("/")[-1]) for r in repos):
            total += dir_bytes(os.path.join(cache, name))
    return total


# ---------------------------------------------------------------- supplier text (mirror of dealdesk/lib/evalrows.ts)
def _one(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


EVIDENCE_PARTS = (("products", "p", 170), ("industries", "in", 60), ("site title", "wt", 60), ("supplied under contracts", "sp", 110),
                  ("customs headings", "hd", 70), ("commodity tags", "cm", 40), ("HS codes", "hs", 40))


def evidence_text(s):
    out = []
    for label, key, n in EVIDENCE_PARTS:
        t = _one(s.get(key))
        if t:
            out.append(f"{label}: {t[:n - 3] + '...' if len(t) > n else t}")
    return " | ".join(out)[:400]


_SUFFIX = re.compile(r"\b(co|corp|corporation|inc|ltd|limited|llc|gmbh|sa|s\.a\.|spa|s\.p\.a\.|srl|bv|ag|plc|pte|pvt|private|company|the)\b", re.ASCII)


def dedupe_key(s):
    """Same as dedupeKey in dealdesk/lib/supmatch.ts (lower case, legal suffixes removed, punctuation to spaces) + country."""
    name = _SUFFIX.sub("", str(s.get("n") or "").lower())
    name = re.sub(r"[\W_]+", " ", name).strip()
    return f"{name}|{s.get('c') or ''}"


def cmd_universe(a):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import base64
    key = os.environ.get("WEB_INDEX_KEY", "")
    if not key:
        raise SystemExit("WEB_INDEX_KEY is not set")
    b = open(a.src, "rb").read()
    plain = AESGCM(base64.b64decode(key)).decrypt(b[:12], b[12:], None)   # body followed by the 16-byte tag
    rows = json.loads(gzip.decompress(plain).decode("utf-8"))
    seen, kept, empty, chars = {}, 0, 0, 0
    # keep one record per company: the first one, or the one that has a website title (as the evaluation does)
    for i, s in enumerate(rows):
        k = dedupe_key(s)
        if k not in seen or (s.get("wt") and not rows[seen[k]].get("wt")):
            seen[k] = i
    # completed records first (a product description or an official website), so a partial run covers them
    prio = lambda s: bool(_one(s.get("p")) or _one(s.get("web")))
    order = sorted(seen.items(), key=lambda kv: (not prio(rows[kv[1]]), kv[1]))
    n_prio = 0
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for k, i in order:
            s = rows[i]
            t = evidence_text(s)
            if not t:
                empty += 1
                t = _one(s.get("n"))
            if not t:
                continue
            chars += len(t)
            kept += 1
            n_prio += prio(s)
            f.write(json.dumps({"i": i, "key": k, "text": t}, ensure_ascii=False) + "\n")
    os.replace(tmp, a.out)
    h = hashlib.sha256(open(a.out, "rb").read()).hexdigest()
    write_json(a.out + ".meta.json", {"records_in_index": len(rows), "companies_after_dedupe": len(seen), "written": kept,
                                      "completed_first": n_prio, "no_evidence_name_only": empty,
                                      "mean_chars": round(chars / max(kept, 1)), "sha256": h})
    say(f"supplier universe: {len(rows)} records in the index, {len(seen)} companies after dedupe, {kept} written "
        f"({n_prio} completed records first: product description or official website; {empty} with no evidence, name only), "
        f"mean text {round(chars / max(kept, 1))} characters, sha256 {h[:12]}")


# ---------------------------------------------------------------- models
def load_embedder(name, cache):
    from fastembed import TextEmbedding
    spec = EMBEDDERS[name]
    if "builtin" in spec:
        return TextEmbedding(spec["builtin"], cache_dir=cache, threads=THREADS), [spec["builtin"]]
    from fastembed.common.model_description import ModelSource, PoolingType
    last = None
    for src in spec["src"]:
        alias = f"sinder/{slug(name)}-{slug(src.split('/')[0])}"
        try:
            try:
                TextEmbedding.add_custom_model(model=alias, pooling=PoolingType.MEAN, normalization=True, sources=ModelSource(hf=src),
                                               dim=spec["dim"], model_file=spec["file"], license=spec["lic"])
            except ValueError:
                pass   # registered earlier in this process
            return TextEmbedding(alias, cache_dir=cache, threads=THREADS), [src]
        except Exception as e:   # the next source; the reason goes to the server-only error file
            last = e
            say(f"  source {src} did not load ({type(e).__name__}); trying the next one")
    raise last


def load_reranker(name, cache):
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    spec = RERANKERS[name]
    return TextCrossEncoder(spec["builtin"], cache_dir=cache, threads=THREADS), [spec["builtin"]]


def embed(model, texts, batch=32):
    import numpy as np
    return np.asarray(list(model.embed(texts, batch_size=batch)), dtype="float32")


def eval_pool(data):
    """Tuning rows that carry a label, grouped by request; refuses any id outside the tuning half."""
    rows = read_jsonl(os.path.join(data, "rows.jsonl"))
    labels = {}
    for r in read_jsonl(os.path.join(data, "labels.jsonl")):
        qid = str(r.get("query_id") or "").strip()
        try:
            rank = int(r.get("rank") or 0)
        except (TypeError, ValueError):
            continue
        lab = str(r.get("label") or "").strip().lower().replace(" ", "_")
        if rank > 0 and lab in LABELS:
            labels[(qid, rank)] = lab
    by_q = {}
    for r in rows:
        qid = str(r.get("query_id"))
        if qid not in TUNING_IDS:
            raise SystemExit("the rows file holds an id outside the tuning half: stopped")
        by_q.setdefault(qid, []).append(r)
    for q in by_q.values():
        q.sort(key=lambda r: int(r["rank"]))
    return by_q, labels


def sup_text(r):
    return _one(r.get("evidence")) or _one(r.get("supplier"))


def cmd_bench(a):
    t_start = time.time()
    by_q, labels = eval_pool(a.data)
    kind = "embed" if a.model in EMBEDDERS else "rerank"
    spec = EMBEDDERS.get(a.model) or RERANKERS[a.model]
    sp = slug(a.model)
    say(f"== {kind} model {a.model} (licence {spec['lic']})")
    t0 = time.time()
    try:
        model, repos = (load_embedder if kind == "embed" else load_reranker)(a.model, a.cache)
    except Exception:
        with open(os.path.join(a.data, f"error_{sp}.txt"), "w") as f:
            f.write(traceback.format_exc())
        say("  the model did not load: skipped (the reason is in the server-only work folder)")
        write_json(os.path.join(a.data, f"speed_{sp}.json"), {"model": a.model, "kind": kind, "licence": spec["lic"], "loaded": False})
        return
    load_s = time.time() - t0
    size = cache_size_for(a.cache, repos)
    say(f"  loaded in {load_s:.0f} s; files on disk {size / 2**20:.0f} MB")

    out, n_pairs, t_score = [], 0, 0.0
    for qid in sorted(by_q):
        pool = [r for r in by_q[qid] if (qid, int(r["rank"])) in labels]
        if not pool:
            continue
        q = _one(pool[0].get("query"))
        docs = [sup_text(r) for r in pool]
        t1 = time.time()
        if kind == "embed":
            qv = embed(model, [spec["q"] + q])[0]
            dv = embed(model, [spec["d"] + d for d in docs])
            scores = (dv @ qv).tolist()
        else:
            scores = [float(x) for x in model.rerank(q, docs, batch_size=16)]
        t_score += time.time() - t1
        n_pairs += len(docs)
        for r, s in zip(pool, scores):
            out.append({"query_id": qid, "rank": int(r["rank"]), "score": round(s, 6)})
    with open(os.path.join(a.data, f"scores_{sp}.jsonl"), "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o) + "\n")
    say(f"  scored {n_pairs} labelled rows of {len({o['query_id'] for o in out})} tuning requests in {t_score:.1f} s")

    # throughput on real supplier texts (the universe sample), as the overnight job and the service would run
    speed = {"model": a.model, "kind": kind, "licence": spec["lic"], "repos": repos, "loaded": True, "load_s": round(load_s, 1),
             "disk_mb": round(size / 2**20), "eval_pairs": n_pairs, "eval_s": round(t_score, 1)}
    sample = []
    if a.universe and os.path.exists(a.universe):
        # an even spread over the whole file (completed records come first and carry longer texts)
        total = json.load(open(a.universe + ".meta.json"))["written"]
        step = max(1, total // a.sample)
        with open(a.universe, encoding="utf-8") as f:
            for n, line in enumerate(f):
                if n % step == 0:
                    sample.append(json.loads(line)["text"])
                    if len(sample) >= a.sample:
                        break
    if sample:
        if kind == "embed":
            embed(model, [spec["d"] + t for t in sample[:64]], batch=a.batch)   # warm up
            t1 = time.time()
            embed(model, [spec["d"] + t for t in sample], batch=a.batch)
            dt = time.time() - t1
            speed.update({"items": len(sample), "items_per_s": round(len(sample) / dt, 1), "batch": a.batch})
            t1 = time.time()
            for i in range(10):
                embed(model, [spec["q"] + sample[i][:80]])
            speed["query_ms"] = round((time.time() - t1) * 100)
            say(f"  throughput: {speed['items_per_s']} supplier texts per second ({len(sample)} texts, batch {a.batch}); "
                f"one query {speed['query_ms']} ms")
        else:
            docs = sample[:200]
            t1 = time.time()
            for i in range(0, len(docs), 50):
                list(model.rerank(sample[i][:80], docs[i:i + 50], batch_size=16))
            dt = time.time() - t1
            speed.update({"items": len(docs), "items_per_s": round(len(docs) / dt, 1), "rerank_50_ms": round(dt / (len(docs) / 50) * 1000)})
            say(f"  throughput: {speed['items_per_s']} pairs per second; re-ranking 50 candidates takes {speed['rerank_50_ms']} ms")
    speed["rss_peak_mb"] = peak_rss_mb()
    speed["cgroup_peak_mb"] = cgroup_peak_mb()
    speed["wall_s"] = round(time.time() - t_start)
    say(f"  memory peak: process {speed['rss_peak_mb']} MB, container {speed['cgroup_peak_mb']} MB (includes file cache)")
    write_json(os.path.join(a.data, f"speed_{sp}.json"), speed)


# ---------------------------------------------------------------- report
def strata_of(data):
    st = {}
    p = os.path.join(data, "tenders.jsonl")
    if os.path.exists(p):
        for t in read_jsonl(p):
            st[str(t.get("query_id"))] = str(t.get("stratum") or "")
    for r in read_jsonl(os.path.join(data, "labels.jsonl")):   # rank 0: the labeller's stratum overrules
        lab = str(r.get("label") or "").strip().lower().replace(" ", "_")
        try:
            rank = int(r.get("rank") or 0)
        except (TypeError, ValueError):
            continue
        if rank == 0 and lab in ("goods", "non_goods", "mixed"):
            st[str(r.get("query_id")).strip()] = lab
    return st


def top_counts(ranks, labels, qid):
    labs = [labels.get((qid, k)) for k in ranks[:10]]
    c = {k: sum(1 for x in labs if x == k) for k in LABELS}
    c["unlabelled"] = sum(1 for x in labs if x is None)
    c["n"] = len(labs)
    return c


def cmd_report(a):
    by_q, labels = eval_pool(a.data)
    strata = strata_of(a.data)
    methods = [("baseline", None)]
    speeds = {}
    for name in list(EMBEDDERS) + list(RERANKERS):
        p = os.path.join(a.data, f"scores_{slug(name)}.jsonl")
        sp = os.path.join(a.data, f"speed_{slug(name)}.json")
        if os.path.exists(sp):
            speeds[name] = json.load(open(sp))
        if os.path.exists(p):
            methods.append((name, {(o["query_id"], o["rank"]): o["score"] for o in read_jsonl(p)}))
    per_q, detail = {}, []
    for qid in sorted(set(TUNING_IDS)):
        rows = by_q.get(qid, [])
        st = "product" if qid.startswith("Q") else (strata.get(qid) or "unknown")
        pool = [int(r["rank"]) for r in rows if (qid, int(r["rank"])) in labels]
        e = {"query_id": qid, "stratum": st, "returned": len(rows), "labelled_pool": len(pool),
             "pool_relevant": sum(1 for k in pool if labels[(qid, k)] == "relevant"),
             "pool_partly": sum(1 for k in pool if labels[(qid, k)] == "partly")}
        for name, sc in methods:
            if sc is None:
                order = [int(r["rank"]) for r in rows]           # what the user sees, unlabelled rows included
            else:
                order = sorted(pool, key=lambda k: (-sc.get((qid, k), float("-inf")), k))
                if any((qid, k) not in sc for k in pool):
                    e.setdefault("missing_scores", []).append(name)
            e[name] = top_counts(order, labels, qid)
            if sc is not None:
                for pos, k in enumerate(order, 1):
                    detail.append({"query_id": qid, "method": name, "new_position": pos, "original_rank": k, "label": labels[(qid, k)],
                                   "score": sc.get((qid, k))})
        per_q[qid] = e
    groups = {s: [e for e in per_q.values() if e["stratum"] == s] for s in STRATA}
    other = sorted({e["stratum"] for e in per_q.values()} - set(STRATA))
    for s in other:
        groups[s] = [e for e in per_q.values() if e["stratum"] == s]
    groups["all"] = list(per_q.values())
    summary = {"tuning_ids": len(TUNING_IDS), "requests_with_rows": sum(1 for e in per_q.values() if e["returned"]),
               "methods": [m for m, _ in methods], "speed": speeds, "per_stratum": {}, "per_request": per_q,
               "rule": "relevant-in-top-10 per request (a request with no rows counts 0 of 10); only labelled rows are re-ordered; ties keep the original rank"}
    say("")
    say("== relevant in top 10, TUNING half only (sums over requests; a request with no rows counts 0)")
    say("   stratum: requests (with rows) | labelled rows in pool, of which relevant / partly | per method: relevant, partly, "
        "requests with 0 relevant, unlabelled in top 10")
    for s, es in groups.items():
        if not es:
            continue
        g = {"requests": len(es), "with_rows": sum(1 for e in es if e["returned"]), "pool": sum(e["labelled_pool"] for e in es),
             "pool_relevant": sum(e["pool_relevant"] for e in es), "pool_partly": sum(e["pool_partly"] for e in es),
             "max_relevant_in_top10": sum(min(10, e["pool_relevant"]) for e in es)}
        say(f"-- {s}: {g['requests']} requests ({g['with_rows']} with rows) | pool {g['pool']} rows, {g['pool_relevant']} relevant / "
            f"{g['pool_partly']} partly | best possible relevant in top 10: {g['max_relevant_in_top10']}")
        for name, _ in methods:
            rel = sum(e[name]["relevant"] for e in es)
            par = sum(e[name]["partly"] for e in es)
            zero = sum(1 for e in es if e[name]["relevant"] == 0)
            unl = sum(e[name]["unlabelled"] for e in es)
            ct = sum(e[name]["cannot_tell"] for e in es)
            shown = sum(e[name]["n"] for e in es)
            g[name] = {"relevant": rel, "partly": par, "irrelevant": sum(e[name]["irrelevant"] for e in es), "cannot_tell": ct,
                       "unlabelled": unl, "rows_in_top10": shown, "requests_zero_relevant": zero,
                       "mean_relevant_per_request": round(rel / len(es), 2)}
            if name != "baseline":
                g[name]["requests_better"] = sum(1 for e in es if e[name]["relevant"] > e["baseline"]["relevant"])
                g[name]["requests_worse"] = sum(1 for e in es if e[name]["relevant"] < e["baseline"]["relevant"])
            extra = "" if name == "baseline" else f", better on {g[name]['requests_better']} / worse on {g[name]['requests_worse']} requests"
            say(f"   {name:<40} relevant {rel:>3} of {shown:>3} shown (mean {rel / len(es):.2f} per request of 10), partly {par:>3}, "
                f"cannot_tell {ct}, 0-relevant requests {zero}, unlabelled in top 10 {unl}{extra}")
        summary["per_stratum"][s] = g
    unl_any = sum(e[n]["unlabelled"] for e in per_q.values() for n, sc in methods if sc is not None)
    say(f"check: unlabelled rows in any re-ordered top 10: {unl_any} (must be 0); "
        f"rows left out of the pools because they carry no label: {sum(e['returned'] - e['labelled_pool'] for e in per_q.values())}")
    summary["unlabelled_in_reordered_top10"] = unl_any
    write_json(os.path.join(a.data, "summary.json"), summary)
    with open(os.path.join(a.data, "detail.jsonl"), "w", encoding="utf-8") as f:
        for d in detail:
            f.write(json.dumps(d) + "\n")
    say("")
    say("== models")
    for name, s in speeds.items():
        if not s.get("loaded"):
            say(f"   {name}: did not load")
            continue
        say(f"   {name}: {s['kind']}, licence {s['licence']}, files {s['disk_mb']} MB, load {s['load_s']} s, "
            f"throughput {s.get('items_per_s', 'n/a')} per s, memory peak {s['rss_peak_mb']} MB (container {s['cgroup_peak_mb']} MB)"
            + (f", one query {s['query_ms']} ms" if "query_ms" in s else "") + (f", re-rank 50 in {s['rerank_50_ms']} ms" if "rerank_50_ms" in s else ""))


# ---------------------------------------------------------------- the whole universe
def cmd_embed(a):
    import numpy as np
    meta = json.load(open(a.universe + ".meta.json"))
    out = os.path.join(a.out, f"{slug(a.model)}-{meta['sha256'][:12]}")
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    spec = EMBEDDERS[a.model]
    total = min(meta["written"], a.limit) if a.limit else meta["written"]   # a limit embeds the first (completed) records only
    parts = (total + a.part - 1) // a.part
    done = sorted(int(p[5:10]) for p in os.listdir(os.path.join(out, "parts")) if p.startswith("part-") and p.endswith(".npy"))
    say(f"universe {total} companies in {parts} parts of {a.part}; {len(done)} parts already done; vectors in a folder named {os.path.basename(out)}")
    model, _ = load_embedder(a.model, a.cache)
    t0, n_new = time.time(), 0
    with open(a.universe, encoding="utf-8") as f:
        part, buf, ids = 0, [], []
        for n, line in enumerate(f):
            if n >= total:
                break
            rec = json.loads(line)
            buf.append(spec["d"] + rec["text"])
            ids.append([rec["i"], rec["key"]])
            if len(buf) == a.part:
                n_new += _part(np, model, out, part, buf, ids, done, a.batch)
                part, buf, ids = part + 1, [], []
                _progress(out, part, parts, n_new, t0)
        if buf:
            n_new += _part(np, model, out, part, buf, ids, done, a.batch)
            part += 1
            _progress(out, part, parts, n_new, t0)
    # one file for the service: the vectors and the ids, in universe order
    vecs = [np.load(os.path.join(out, "parts", f"part-{i:05d}.npy")) for i in range(parts)]
    np.save(os.path.join(out, "vectors.f16.npy.tmp.npy"), np.concatenate(vecs))
    os.replace(os.path.join(out, "vectors.f16.npy.tmp.npy"), os.path.join(out, "vectors.f16.npy"))
    with open(os.path.join(out, "ids.jsonl.tmp"), "w", encoding="utf-8") as g:
        for i in range(parts):
            for x in json.load(open(os.path.join(out, "parts", f"part-{i:05d}.ids.json"), encoding="utf-8")):
                g.write(json.dumps({"i": x[0], "key": x[1]}, ensure_ascii=False) + "\n")
    os.replace(os.path.join(out, "ids.jsonl.tmp"), os.path.join(out, "ids.jsonl"))
    write_json(os.path.join(out, "manifest.json"), {"model": a.model, "licence": spec["lic"], "dim": spec["dim"], "dtype": "float16",
                                                    "normalized": True, "count": total, "universe_total": meta["written"], "universe_sha256": meta["sha256"],
                                                    "query_prefix": spec["q"], "document_prefix": spec["d"], "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    say(f"finished: {total} vectors of {spec['dim']} dimensions (float16) in {time.time() - t0:.0f} s this session")
    open(os.path.join(a.out, "LATEST"), "w").write(os.path.basename(out) + "\n")


def _part(np, model, out, i, texts, ids, done, batch):
    if i in done:
        return 0
    v = embed(model, texts, batch=batch).astype("float16")
    np.save(os.path.join(out, "parts", f"part-{i:05d}.tmp.npy"), v)
    with open(os.path.join(out, "parts", f"part-{i:05d}.ids.json"), "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False)
    os.replace(os.path.join(out, "parts", f"part-{i:05d}.tmp.npy"), os.path.join(out, "parts", f"part-{i:05d}.npy"))
    return len(texts)


def _progress(out, part, parts, n_new, t0):
    dt = time.time() - t0
    rate = n_new / dt if dt > 0 else 0
    p = {"parts_done": part, "parts": parts, "embedded_this_session": n_new, "per_s": round(rate, 1), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    write_json(os.path.join(out, "progress.json"), p)
    say(f"progress: part {part} of {parts}, {n_new} embedded this session, {rate:.1f} per s")


# ---------------------------------------------------------------- query service
def cmd_serve(a):
    import numpy as np
    d = os.path.join(a.out, open(os.path.join(a.out, "LATEST")).read().strip())
    man = json.load(open(os.path.join(d, "manifest.json")))
    vecs = np.load(os.path.join(d, "vectors.f16.npy"), mmap_mode="r")
    ids = [json.loads(line) for line in open(os.path.join(d, "ids.jsonl"), encoding="utf-8")]
    model, _ = load_embedder(man["model"], a.cache)
    chunk = 65536

    def search(q, n):
        qv = embed(model, [man["query_prefix"] + q])[0].astype("float32")
        best_s, best_i = np.empty(0, dtype="float32"), np.empty(0, dtype="int64")
        for s in range(0, len(vecs), chunk):
            sc = np.asarray(vecs[s:s + chunk], dtype="float32") @ qv
            k = min(n, len(sc))
            top = np.argpartition(-sc, k - 1)[:k]
            best_s, best_i = np.concatenate([best_s, sc[top]]), np.concatenate([best_i, top + s])
        o = np.argsort(-best_s)[:n]
        return [{"i": ids[j]["i"], "key": ids[j]["key"], "score": round(float(best_s[x]), 4)} for x, j in zip(o, best_i[o])]

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/health":
                return self._send(200, {"ok": True, "count": len(ids), "model": man["model"]})
            if u.path != "/search":
                return self._send(404, {"error": "not found"})
            qs = urllib.parse.parse_qs(u.query)
            q = (qs.get("q") or [""])[0].strip()[:500]
            try:
                n = max(1, min(500, int((qs.get("n") or ["50"])[0])))
            except ValueError:
                n = 50
            if not q:
                return self._send(400, {"error": "q is empty"})
            t0 = time.time()
            res = search(q, n)
            return self._send(200, {"model": man["model"], "ms": round((time.time() - t0) * 1000), "results": res})

        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *args):   # no request text in any log
            pass

    say(f"semantic search service: {len(ids)} suppliers, model {man['model']}, listening on port {a.port}")
    http.server.ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("universe"); u.add_argument("--src", required=True); u.add_argument("--out", required=True)
    b = sub.add_parser("bench"); b.add_argument("--data", required=True); b.add_argument("--model", required=True)
    b.add_argument("--cache", required=True); b.add_argument("--universe", default=""); b.add_argument("--sample", type=int, default=2000)
    b.add_argument("--batch", type=int, default=32)
    r = sub.add_parser("report"); r.add_argument("--data", required=True)
    e = sub.add_parser("embed"); e.add_argument("--universe", required=True); e.add_argument("--out", required=True)
    e.add_argument("--model", required=True); e.add_argument("--cache", required=True); e.add_argument("--part", type=int, default=8192)
    e.add_argument("--batch", type=int, default=32)
    e.add_argument("--limit", type=int, default=0)
    s = sub.add_parser("serve"); s.add_argument("--out", required=True); s.add_argument("--cache", required=True); s.add_argument("--port", type=int, default=8099)
    a = p.parse_args(argv)
    {"universe": cmd_universe, "bench": cmd_bench, "report": cmd_report, "embed": cmd_embed, "serve": cmd_serve}[a.cmd](a)


if __name__ == "__main__":
    main()
