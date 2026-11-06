#!/usr/bin/env python3
"""Offline NDJSON checks. No network, production writes or delivery verification."""
import argparse
import hashlib
import ipaddress
import json
import re
import sys
from collections import Counter
from urllib.parse import urlparse


def website_host(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        u = urlparse(value.strip())
        h = (u.hostname or '').lower().rstrip('.')
        if u.scheme not in ('http', 'https') or not h or u.username or u.password:
            return None
        if h == 'localhost' or h.endswith(('.local', '.internal')):
            return None
        try:
            if not ipaddress.ip_address(h).is_global:
                return None
        except ValueError:
            if '.' not in h:
                return None
        return h.removeprefix('www.')
    except (ValueError, TypeError):
        return None


def email_shape(value):
    return isinstance(value, str) and bool(re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value.strip()))


def phone_shape(value):
    if not isinstance(value, str):
        return False
    p = re.sub(r'[\s().-]', '', value)
    return bool(re.fullmatch(r'\+[1-9][0-9]{6,14}', p))


def contact_checks(row):
    host = website_host(row.get('website'))
    out = []
    for kind, valid in [('email', email_shape), ('phone', phone_shape)]:
        value = row.get(kind)
        if not value:
            continue
        shaped = valid(value)
        attributed = shaped and any(
            e.get('kind') == kind and e.get('value') == value and
            host is not None and website_host(e.get('url')) == host and
            bool(e.get('checked_at'))
            for e in row.get('contact_evidence', []) if isinstance(e, dict))
        out.append({'kind': kind, 'value': value, 'structurally_plausible': shaped,
                    'official_attribution_claimed': attributed,
                    'delivery_or_response_verified': False})
    for e in row.get('contact_evidence', []):
        if not isinstance(e, dict) or e.get('kind') != 'form':
            continue
        url = e.get('value')
        out.append({'kind': 'form', 'value': url,
                    'structurally_plausible': website_host(url) is not None,
                    'official_attribution_claimed': bool(host and website_host(url) == host and e.get('checked_at')),
                    'delivery_or_response_verified': False})
    return out


def check_row(row):
    if not isinstance(row, dict):
        raise ValueError('Each row must be a JSON object')
    contacts = contact_checks(row)
    flags = [c['kind'] + '_invalid_shape' for c in contacts if not c['structurally_plausible']]
    if row.get('website') and not website_host(row.get('website')):
        flags.append('website_invalid_or_private_literal')
    if row.get('entity_kind') in ('article', 'topic', 'country', 'unknown_nonbusiness'):
        flags.append('not_a_business_entity')
    gaps = [f for f in ('name', 'website', 'products', 'role') if not row.get(f)]
    if not any(c['official_attribution_claimed'] for c in contacts):
        gaps.append('source_attributed_contact')
    normalized_name = re.sub(r'\W+', ' ', str(row.get('name') or '').casefold()).strip()
    return {'id': row.get('id'), 'name_key': normalized_name,
            'domain_key': website_host(row.get('website')), 'flags': flags,
            'gaps': gaps, 'contacts': contacts, 'raw_preserved': True,
            'scope': 'offline_structure_and_supplied_attribution_only'}


def cache_key(payload, workspace_id, processing_version):
    if not workspace_id or not processing_version:
        raise ValueError('Explicit workspace scope and processing version required')
    raw = json.dumps([workspace_id, processing_version, payload], sort_keys=True,
                     ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', help='NDJSON input path; never modified')
    ap.add_argument('--output', help='Proposed checks NDJSON path; use a fresh file')
    args = ap.parse_args()
    counts, domains = Counter(), Counter()
    target = open(args.output, 'x', encoding='utf-8') if args.output else None
    try:
        with open(args.input, encoding='utf-8') as src:
            for line in src:
                if not line.strip():
                    continue
                counts['attempted'] += 1
                try:
                    result = check_row(json.loads(line))
                    counts['processed'] += 1
                    counts['with_gaps'] += bool(result['gaps'])
                    counts['with_flags'] += bool(result['flags'])
                    counts['with_attribution_claimed'] += any(c['official_attribution_claimed'] for c in result['contacts'])
                    if result['domain_key']:
                        domains[result['domain_key']] += 1
                except (ValueError, TypeError, AttributeError) as err:
                    counts['unresolved'] += 1
                    result = {'status': 'input_error', 'line': counts['attempted'], 'error': str(err)}
                if target:
                    target.write(json.dumps(result, ensure_ascii=False) + '\n')
        counts['shared_domain_candidate_groups'] = sum(v > 1 for v in domains.values())
        print(json.dumps({'counts': counts, 'network_checks': 0,
                          'production_writes': 0, 'scope': 'offline checks, not completed enrichment'}))
    finally:
        if target:
            target.close()


if __name__ == '__main__':
    main()
