#!/usr/bin/env python3
"""Offline dossier gates. Never grants authorization or performs actions."""
import argparse
import json
import re
from datetime import datetime, timezone


STAGES = ('research', 'ready_for_rfq', 'quoted', 'reviewed')


def contact_shape(contact):
    value = contact.get('value')
    if not isinstance(value, str):
        return False
    if contact.get('kind') == 'phone':
        return bool(re.fullmatch(r'\+[1-9][0-9]{6,14}', re.sub(r'[\s().-]', '', value)))
    if contact.get('kind') == 'email':
        return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value))
    if contact.get('kind') == 'form':
        from urllib.parse import urlparse
        u = urlparse(value)
        return u.scheme in ('https', 'http') and bool(u.hostname) and not u.username and not u.password
    return False


def instant(value):
    t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timestamp requires timezone')
    return t


def validate(dossier, target, as_of):
    if target not in STAGES:
        raise ValueError('Target outside helper scope; execution authorization is a host action')
    now = instant(as_of)
    errors = []
    for field in ('workspace_id', 'actor_id', 'deal_id'):
        if not dossier.get(field):
            errors.append('missing_' + field)
    req = dossier.get('requirements') or {}
    if not req.get('product'):
        errors.append('missing_product')
    level = STAGES.index(target)
    if level >= 1:
        usable = [s for s in dossier.get('suppliers', [])
                  if s.get('match_state') in ('supported', 'plausible') and
                  s.get('evidence_ids') and any(c.get('source_url') and
                  c.get('state') == 'published' and c.get('kind') in ('email', 'phone', 'form')
                  and c.get('structurally_valid') is True and contact_shape(c) for c in s.get('contacts', []))]
        if not usable:
            errors.append('no_supplier_with_sourced_match_and_contact')
        if not dossier.get('route_options'):
            errors.append('missing_route_options')
    if level >= 2:
        valid_quotes = []
        for q in dossier.get('quotes', []):
            try:
                current = instant(q.get('valid_until')) >= now
            except (ValueError, TypeError):
                current = False
            if q.get('status') == 'actual_offer' and q.get('source_document') and q.get('supplier_id') and current:
                valid_quotes.append(q)
        if not valid_quotes:
            errors.append('no_current_documented_actual_offer')
    if level >= 3:
        if not dossier.get('economics'):
            errors.append('missing_economics')
        if not dossier.get('review') or dossier['review'].get('verdict') != 'completed':
            errors.append('review_not_completed')
    return {'target': target, 'data_gate_passed': not errors, 'errors': errors,
            'validation_only': True, 'authorization_checked': False,
            'requires_host_authorization': True,
            'execution_approved': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', help='Dossier JSON')
    ap.add_argument('--target', choices=STAGES, default='research')
    ap.add_argument('--as-of', default=datetime.now(timezone.utc).isoformat())
    args = ap.parse_args()
    with open(args.input, encoding='utf-8') as stream:
        print(json.dumps(validate(json.load(stream), args.target, args.as_of)))


if __name__ == '__main__':
    main()
