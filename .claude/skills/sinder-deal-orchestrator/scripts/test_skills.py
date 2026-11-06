#!/usr/bin/env python3
"""Offline regression tests; no web/model/API calls or live writes."""
import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def locate(name):
    for p in ROOT.iterdir():
        f = p / 'SKILL.md'
        if f.is_file() and ('name: ' + name + '\n') in f.read_text():
            return p
    raise RuntimeError('Required sibling skill unavailable: ' + name)


def module(name, script):
    path = locate(name) / 'scripts' / script
    spec = importlib.util.spec_from_file_location(script.replace('.', '_'), path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


REFINE = module('sinder-data-refinement', 'refine_records.py')
MATCH = module('sinder-supplier-matching', 'match_guard.py')
MATH = module('sinder-deal-economics', 'deal_math.py')
STATE = module('sinder-deal-orchestrator', 'deal_state.py')


def candidate(**fields):
    return {'entity_kind': 'company', 'assertions': [
        {'property': k, 'value': v, 'evidence_id': 'synthetic-evidence', 'status': 'source_statement'}
        for k, v in fields.items()]}


class ContactTests(unittest.TestCase):
    def test_bad_phone(self):
        self.assertFalse(REFINE.phone_shape('+04900491'))

    def test_plausible_phone_is_not_deliverability(self):
        x = REFINE.check_row({'id': 'synthetic', 'phone': '+12025550123'})
        self.assertTrue(x['contacts'][0]['structurally_plausible'])
        self.assertFalse(x['contacts'][0]['delivery_or_response_verified'])

    def test_local_phone_not_invented_country(self):
        self.assertFalse(REFINE.phone_shape('020 1234 5678'))

    def test_email_attribution_needs_source(self):
        self.assertFalse(REFINE.check_row({'email': 'sales@mill.example'})['contacts'][0]['official_attribution_claimed'])

    def test_form_can_be_useful(self):
        x = REFINE.check_row({'website': 'https://mill.example', 'contact_evidence': [
            {'kind': 'form', 'value': 'https://mill.example/contact', 'checked_at': '2026-11-06'}]})
        self.assertTrue(x['contacts'][0]['official_attribution_claimed'])

    def test_private_literal_blocked(self):
        for url in ['http://127.0.0.1/x', 'http://169.254.169.254', 'http://localhost', 'http://x.internal', 'https://user:pass@mill.example']:
            self.assertIsNone(REFINE.website_host(url))

    def test_cache_separates_tenants(self):
        self.assertNotEqual(REFINE.cache_key({'x': 1}, 'a', 'v1'), REFINE.cache_key({'x': 1}, 'b', 'v1'))

    def test_streaming_cli_reports_errors_without_enrichment_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp) / 'rows.ndjson'
            src.write_text('{"id":"a","name":"Mill"}\nINVALID\n')
            out = subprocess.check_output(['python3', str(locate('sinder-data-refinement')/'scripts/refine_records.py'), str(src)], text=True)
            result = json.loads(out)
            self.assertEqual(result['counts']['attempted'], 2)
            self.assertEqual(result['counts']['unresolved'], 1)
            self.assertEqual(result['production_writes'], 0)


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.req = {'mandatory': {'product_family': 'maize', 'color': 'white', 'form': 'whole grain'}}

    def test_exact_supported(self):
        self.assertEqual(MATCH.classify(self.req, candidate(product_family='maize', color='white', form='whole grain'))['state'], 'supported')

    def test_yellow_conflicts(self):
        self.assertEqual(MATCH.classify(self.req, candidate(product_family='maize', color='yellow', form='whole grain'))['state'], 'incompatible')

    def test_unknown_color_stays_research(self):
        self.assertEqual(MATCH.classify(self.req, candidate(product_family='maize'))['state'], 'plausible')

    def test_company_name_cannot_establish_product(self):
        c = {'entity_kind': 'company', 'name': 'Corning', 'assertions': []}
        self.assertNotEqual(MATCH.classify(self.req, c)['state'], 'supported')

    def test_topic_is_not_supplier(self):
        c = candidate(product_family='maize', color='white', form='whole grain')
        c['entity_kind'] = 'topic'
        self.assertEqual(MATCH.classify(self.req, c)['state'], 'research')

    def test_corn_dogs_not_whole_grain(self):
        c = candidate(product_family='maize', form='prepared snack')
        self.assertEqual(MATCH.classify(self.req, c)['state'], 'incompatible')

    def test_wire_rod_not_flat_coil(self):
        req = {'mandatory': {'product_family': 'steel', 'form': 'flat coil', 'processing': 'hot rolled'}}
        self.assertEqual(MATCH.classify(req, candidate(product_family='steel', form='wire rod', processing='hot rolled'))['state'], 'incompatible')

    def test_medical_urea_not_fertilizer(self):
        req = {'mandatory': {'product_family': 'urea fertilizer'}}
        self.assertEqual(MATCH.classify(req, candidate(product_family='urea breath test'))['state'], 'incompatible')

    def test_automotive_filter_not_ro(self):
        req = {'mandatory': {'product_family': 'reverse osmosis system'}}
        self.assertEqual(MATCH.classify(req, candidate(product_family='automotive filter'))['state'], 'incompatible')

    def test_unsourced_assertions_not_supported(self):
        c = candidate(product_family='maize', color='white', form='whole grain')
        for a in c['assertions']:
            a['evidence_id'] = None
        self.assertNotEqual(MATCH.classify(self.req, c)['state'], 'supported')


class EconomicsTests(unittest.TestCase):
    def base(self):
        return {'model': 'principal', 'currency': 'USD', 'quantity': 100, 'unit': 'item',
                'purchase_unit': 10, 'sale_unit': 15,
                'costs': [{'name': 'freight', 'amount': 100, 'basis': 'total'},
                          {'name': 'handling', 'amount': 50, 'basis': 'total'}]}

    def test_golden_contribution(self):
        self.assertEqual(Decimal(MATH.calculate(self.base())['contribution_before_finance']), Decimal(350))

    def test_missing_ledger_does_not_invent_finance(self):
        self.assertIsNone(MATH.calculate(self.base())['contribution_after_finance'])

    def test_peak_funding_includes_interest(self):
        x = self.base()
        x.update(cash_events=[{'day': 0, 'amount': -1150}, {'day': 30, 'amount': 1500}], annual_finance_rate='0.12', funding_limit=1150)
        out = MATH.calculate(x)
        expected = Decimal(1150)*Decimal('.12')*Decimal(30)/Decimal(365)
        self.assertEqual(Decimal(out['finance_cost']), expected)
        self.assertEqual(out['funding_capacity'], 'exceeds_supplied_limit')
        self.assertEqual(out['warnings'], [])

    def test_nan_rejected(self):
        for value in ['NaN', 'Infinity', True, None]:
            x = self.base(); x['purchase_unit'] = value
            with self.assertRaises(ValueError):
                MATH.calculate(x)

    def test_percent_not_decimal_rejected(self):
        with self.assertRaises(ValueError):
            MATH.calculate({'model':'agency', 'currency':'USD', 'commission_basis':100000, 'commission_rate':8})

    def test_agency_not_full_contract_revenue(self):
        out = MATH.calculate({'model':'agency','currency':'USD','commission_basis':100000,'commission_rate':'.08','costs':[{'name':'work','amount':1000,'basis':'total'}]})
        self.assertEqual(Decimal(out['revenue']), Decimal(8000))
        self.assertEqual(Decimal(out['contribution_before_finance']), Decimal(7000))

    def test_mixed_currency_rejected(self):
        x = self.base(); x['costs'][0]['currency'] = 'EUR'
        with self.assertRaises(ValueError): MATH.calculate(x)

    def test_ledger_scope_warning(self):
        x = self.base(); x.update(cash_events=[{'day':0,'amount':-1000}],annual_finance_rate=0)
        self.assertTrue(MATH.calculate(x)['warnings'])


class StageTests(unittest.TestCase):
    def base(self):
        return {'workspace_id':'synthetic-w','actor_id':'synthetic-a','deal_id':'synthetic-d',
                'requirements':{'product':'white maize'},'route_options':[{'route':'local_partner','state':'conditional'}],
                'suppliers':[{'match_state':'plausible','evidence_ids':['synthetic-e1'],
                'contacts':[{'kind':'form','value':'https://mill.example/contact','state':'published','source_url':'https://mill.example/contact','structurally_valid':True}]}]}

    def check(self, d, target): return STATE.validate(d,target,'2026-11-06T10:00:00Z')

    def test_conditional_route_can_prepare_rfq(self):
        self.assertTrue(self.check(self.base(),'ready_for_rfq')['data_gate_passed'])

    def test_invalid_phone_does_not_unlock_rfq(self):
        d=self.base(); d['suppliers'][0]['contacts']=[{'kind':'phone','value':'+04900491','state':'published','source_url':'https://mill.example','structurally_valid':True}]
        self.assertFalse(self.check(d,'ready_for_rfq')['data_gate_passed'])

    def test_quote_missing_or_expired(self):
        d=self.base(); d['quotes']=[{'status':'actual_offer','source_document':'synthetic.pdf','supplier_id':'s','valid_until':'2026-11-01T00:00:00Z'}]
        self.assertFalse(self.check(d,'quoted')['data_gate_passed'])

    def test_indicative_not_actual_quote(self):
        d=self.base(); d['quotes']=[{'status':'indicative','source_document':'synthetic.pdf','supplier_id':'s','valid_until':'2026-12-01T00:00:00Z'}]
        self.assertFalse(self.check(d,'quoted')['data_gate_passed'])

    def test_no_authorization_claim(self):
        out=self.check(self.base(),'ready_for_rfq')
        self.assertFalse(out['authorization_checked'])
        self.assertFalse(out['execution_approved'])

    def test_execution_out_of_scope(self):
        with self.assertRaises(ValueError): self.check(self.base(),'approved_for_execution')


if __name__ == '__main__':
    unittest.main(verbosity=2)
