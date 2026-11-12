"""Development-only diagnostics; no network, credentials, model calls or index writes.

Examples (run on the server with PRIVATE development-only inputs):
 python tools/retrieval_gaps.py --manifest split_manifest.json \
   --requests semantic/summary.json --trace dev_trace.jsonl \
   --labels dev_labels.jsonl --out private/retrieval_gaps.json

Requests: existing semantic per_request, eval_score product/tender per_query,
or a JSON/JSONL list with query_id/id (tools/search_eval.py output accepted).
--requests tools/search_eval.py safely reads its CASES literal via AST, never
imports it or calls suppliers()/Config. Only supplier cases are included.
The frozen manifest's tune list is mandatory. Trace/label files MUST be
prefiltered to that list by the data owner; this program rejects other IDs.

Trace contract, one record/query: query_id, index_version, retrieval_version,
stages={index_hits:[stable IDs],after_filters:[IDs],after_sector:[IDs],
returned:[IDs]}; optional language_blocked=true with language_evidence.
Stages must form nested sets; omitted stages remain unmeasured. 'returned'
is the actual ordered result, not a second retrieval implementation.
Labels: query_id, supplier_id, label; optional in_index=true/false recorded
by the server against this exact index_version. Rank-only labels cannot
establish index availability and are rejected. Unknown/partly are not hits.

Output contains counts/query IDs only. Do not publish private trace/labels.
Availability/recall refer ONLY to the labelled sample, never the whole index.
Without actual traces/labels a causal reason/recall stays unknown. Missing
top-ten slots count zero; judged precision has its own explicit denominator.
"""
import argparse
import ast
import json
from pathlib import Path

STAGES = ('index_hits', 'after_filters', 'after_sector', 'returned')
LABELS = {'relevant', 'partly', 'irrelevant', 'cannot_tell'}


def records(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    if str(path).endswith('.py'):
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CASES' for t in node.targets):
                return [{'query_id': x[0]} for x in ast.literal_eval(node.value) if x[1] == 's']
        raise ValueError('CASES literal not found')
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(obj, list):
        return obj
    if 'per_request' in obj:
        return [dict(v, query_id=k) for k, v in obj['per_request'].items()]
    if 'per_query' in obj:
        return obj['per_query']
    if 'product' in obj or 'tender' in obj:
        return [r for k in ('product', 'tender') for r in obj.get(k, {}).get('per_query', [])]
    return [obj]


def qid(row):
    value = row.get('query_id', row.get('id'))
    if not isinstance(value, str) or not value.strip():
        raise ValueError('query_id required')
    return value.strip()


def count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('count must be a nonnegative integer')
    return value


def unique_ids(values):
    if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values):
        raise ValueError('stage must be a list of stable string supplier IDs')
    if len(values) != len(set(values)):
        raise ValueError('duplicate supplier ID in stage')
    return values


def diagnose(request, trace=None, labels=()):
    query_id = qid(request)
    trace = trace or {}
    if trace and qid(trace) != query_id:
        raise ValueError('trace/query mismatch')
    stages = trace.get('stages', {})
    if not isinstance(stages, dict) or set(stages) - set(STAGES):
        raise ValueError('unknown retrieval stage')
    previous = None
    for stage in STAGES:
        if stage not in stages:
            continue
        ids = unique_ids(stages[stage])
        if previous is not None and not set(ids) <= previous:
            raise ValueError('retrieval stages must be nested')
        previous = set(ids)
    returned = stages.get('returned')
    reported = request.get('returned', request.get('results'))
    if reported is not None:
        count(reported)
    n = len(returned) if returned is not None else reported
    if returned is not None and reported is not None and len(returned) != reported:
        raise ValueError('trace and summary returned counts disagree')
    reason = 'not_zero' if n else 'unknown_uninstrumented'
    if n == 0:
        if stages.get('index_hits') == []:
            reason = 'no_index_hit'
            if trace.get('language_blocked') is True and trace.get('language_evidence'):
                reason = 'language_blocked'
        elif stages.get('index_hits') and stages.get('after_filters') == []:
            reason = 'filter_removed_all'
        elif stages.get('after_filters') and stages.get('after_sector') == []:
            reason = 'sector_removed_all'
    lab = {}
    for row in labels:
        if qid(row) != query_id:
            raise ValueError('label/query mismatch')
        sid, label = row.get('supplier_id'), row.get('label')
        if not isinstance(sid, str) or not sid or label not in LABELS:
            raise ValueError('stable supplier_id and valid label required; rank is insufficient')
        if sid in lab:
            raise ValueError('duplicate label')
        if 'in_index' in row and type(row['in_index']) is not bool:
            raise ValueError('in_index must be boolean')
        if row.get('in_index') is not None and not trace.get('index_version'):
            raise ValueError('index availability requires index_version')
        if row.get('in_index') is False and returned is not None and sid in returned:
            raise ValueError('returned supplier marked absent from index')
        lab[sid] = row
    available_known = bool(lab) and all('in_index' in r for r in lab.values())
    available = sum(r['label'] == 'relevant' and r.get('in_index') is True for r in lab.values()) if available_known else None
    top = returned[:10] if returned is not None else []
    rel = sum(lab.get(s, {}).get('label') == 'relevant' for s in top) if returned is not None else None
    judged = sum(lab.get(s, {}).get('label') in {'relevant', 'partly', 'irrelevant'} for s in top) if returned is not None else None
    retrieved_relevant = sum(lab.get(s, {}).get('label') == 'relevant' for s in returned) if returned is not None else None
    return {'query_id': query_id, 'index_version': trace.get('index_version'),
            'retrieval_version': trace.get('retrieval_version'), 'candidates_returned': n,
            'zero_reason': reason, 'stage_counts': {k: len(v) for k, v in stages.items()},
            'top10_slots': 10, 'relevant_top10': rel, 'judged_top10': judged,
            'unlabelled_top10': sum(s not in lab for s in top) if returned is not None else None,
            'cannot_tell_top10': sum(lab.get(s, {}).get('label') == 'cannot_tell' for s in top) if returned is not None else None,
            'missing_top10_slots': max(0, 10 - n) if n is not None else None,
            'fixed_slot_precision': rel / 10 if rel is not None else None,
            'judged_precision': rel / judged if judged else None,
            'labelled_relevant_in_index': available,
            'labelled_relevant_returned': retrieved_relevant,
            'labelled_sample_recall': retrieved_relevant / available if available and retrieved_relevant is not None else None,
            'availability_scope': 'labelled sample only; not total index relevance',
            'summary_only': returned is None}


def build(requests, manifest, traces=(), labels=()):
    tune, heldout = set(manifest['tune']), set(manifest.get('heldout', []))
    if not tune or tune & heldout:
        raise ValueError('invalid frozen split')
    selected = {}
    for r in requests:
        key = qid(r)
        if key not in tune:
            continue
        if key in selected:
            raise ValueError('duplicate request ID')
        selected[key] = r
    by_trace, by_labels = {}, {}
    for t in traces:
        key = qid(t)
        if key not in selected or key in by_trace:
            raise ValueError('trace outside selected development requests or duplicate trace')
        by_trace[key] = t
    for label in labels:
        key = qid(label)
        if key not in selected:
            raise ValueError('labels must contain selected development requests only')
        by_labels.setdefault(key, []).append(label)
    out = [diagnose(selected[k], by_trace.get(k), by_labels.get(k, [])) for k in sorted(selected)]
    return {'development_only': True, 'requested_development_count': len(tune),
            'requests_observed': len(out), 'missing_development_requests': sorted(tune - set(selected)),
            'top10_denominator': 10 * len(tune), 'per_request': out,
            'warnings': ['No production retrieval was run by this diagnostic.',
                         'No relevance labels are generated; missing trace/labels remain unknown.']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--requests', required=True)
    p.add_argument('--trace')
    p.add_argument('--labels')
    p.add_argument('--out', required=True)
    a = p.parse_args(argv)
    try:
        result = build(records(a.requests), json.loads(Path(a.manifest).read_text()),
                       records(a.trace) if a.trace else [], records(a.labels) if a.labels else [])
        Path(a.out).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except (ValueError, KeyError, OSError, TypeError) as e:
        p.exit(2, 'diagnostic failed: ' + type(e).__name__ + ' (check private inputs)\n')
    print(json.dumps({'requests_observed': result['requests_observed'],
                      'missing_requests': len(result['missing_development_requests']),
                      'trace_missing': sum(r['summary_only'] for r in result['per_request'])}))


if __name__ == '__main__':
    main()
