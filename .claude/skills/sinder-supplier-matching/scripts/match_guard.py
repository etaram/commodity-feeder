#!/usr/bin/env python3
"""Conservative structured-assertion guard; not a semantic search engine."""
import argparse
import json
import re


def norm(value):
    return re.sub(r'\s+', ' ', str(value).strip().casefold())


def classify(requirement, candidate):
    required = requirement.get('mandatory') or {}
    if not required.get('product_family'):
        raise ValueError('mandatory.product_family is required')
    if any(not isinstance(v, str) or not v.strip() for v in required.values()):
        raise ValueError('Mandatory values must be explicit nonempty strings')
    if candidate.get('entity_kind') not in ('company', 'agency', 'plant', 'cooperative'):
        return {'state': 'research', 'reason': 'business_entity_not_established', 'gaps': list(required)}
    grouped = {}
    for a in candidate.get('assertions', []):
        if a.get('evidence_id') and a.get('status') in ('observed', 'source_statement', 'verified'):
            grouped.setdefault(a.get('property'), set()).add(norm(a.get('value')))
    missing, conflicts, matched = [], [], []
    for key, value in required.items():
        expected = norm(value)
        actual = grouped.get(key, set())
        if expected in actual:
            matched.append(key)
        elif actual:
            conflicts.append({'property': key, 'required': value, 'evidenced': sorted(actual)})
        else:
            missing.append(key)
    family = norm(required['product_family'])
    text = norm(candidate.get('evidence_text') or '')
    # Text can raise a review flag; text alone cannot establish a supported match.
    context_flags = []
    if family == 'maize' and norm(required.get('color')) == 'white':
        if 'color' not in matched and re.search(r'\byellow\s+(?:corn|maize)\b', text):
            context_flags.append('yellow_maize_evidence')
        if 'form' not in matched and re.search(r'\b(corn dogs?|cornmeal|corn flakes?|corn starch)\b', text):
            context_flags.append('processed_maize_context')
    if family == 'urea fertilizer' and re.search(r'urea cream|carbamide peroxide|urea breath test|adblue', text):
        context_flags.append('non_fertilizer_context_review')
    if family == 'reverse osmosis system' and re.search(r'automotive|air filters?', text):
        context_flags.append('other_filtration_context_review')
    if family == 'diesel generator' and re.search(r'ice cream|iqf mango|reefer', text):
        context_flags.append('transport_context_review')
    if conflicts:
        state = 'incompatible'
    elif missing or context_flags:
        state = 'plausible'
    else:
        state = 'supported'
    return {'state': state, 'matched': matched, 'gaps': missing,
            'conflicts': conflicts, 'review_flags': context_flags,
            'basis': 'supplied_sourced_assertions_only',
            'capacity_or_availability_verified': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', help='JSON with requirement and candidate')
    args = ap.parse_args()
    with open(args.input, encoding='utf-8') as stream:
        x = json.load(stream)
    print(json.dumps(classify(x['requirement'], x['candidate']), ensure_ascii=False))


if __name__ == '__main__':
    main()
