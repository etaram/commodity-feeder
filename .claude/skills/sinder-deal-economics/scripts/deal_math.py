#!/usr/bin/env python3
"""Single-currency scenario math and a stated Actual/365 cash model."""
import argparse
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def number(value, name, minimum=None):
    if isinstance(value, bool) or value is None:
        raise ValueError(name + ' must be an explicit finite number')
    try:
        out = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(name + ' is not numeric') from exc
    if not out.is_finite() or (minimum is not None and out < minimum):
        raise ValueError(name + ' is nonfinite or out of range')
    return out


def cash_model(events, annual_rate):
    rate = number(annual_rate, 'annual_finance_rate', Decimal(0))
    grouped = defaultdict(lambda: Decimal(0))
    for event in events:
        day = event.get('day')
        if isinstance(day, bool) or not isinstance(day, int) or day < 0:
            raise ValueError('cash event day must be a nonnegative integer')
        grouped[day] += number(event.get('amount'), 'cash amount')
    if not grouped:
        raise ValueError('cash_events must not be empty')
    cash = interest = peak = Decimal(0)
    previous = min(grouped)
    ledger = []
    for day in sorted(grouped):
        charge = max(-cash, Decimal(0)) * rate * Decimal(day - previous) / Decimal(365)
        cash -= charge
        interest += charge
        peak = max(peak, -cash)
        cash += grouped[day]
        peak = max(peak, -cash)
        ledger.append({'day': day, 'cash_flow': str(grouped[day]),
                       'interest_charged': str(charge), 'balance': str(cash)})
        previous = day
    return {'finance_cost': interest, 'peak_funding': peak,
            'closing_cash': cash, 'ledger': ledger}


def calculate(x):
    currency = x.get('currency')
    if not isinstance(currency, str) or not currency.isascii() or not currency.isalpha() or len(currency) != 3:
        raise ValueError('Explicit three-letter currency required; no implicit FX conversion')
    total_costs = Decimal(0)
    for cost in x.get('costs', []):
        if not cost.get('name') or cost.get('basis') != 'total':
            raise ValueError('Each cost requires name and basis=total')
        if cost.get('currency', currency) != currency:
            raise ValueError('Mixed currencies must be normalized before calculation')
        total_costs += number(cost.get('amount'), 'cost amount', Decimal(0))
    model = x.get('model')
    if model == 'principal':
        quantity = number(x.get('quantity'), 'quantity', Decimal(0))
        if quantity <= 0 or not x.get('unit'):
            raise ValueError('Positive quantity and explicit unit required')
        purchase = quantity * number(x.get('purchase_unit'), 'purchase_unit', Decimal(0))
        revenue = quantity * number(x.get('sale_unit'), 'sale_unit', Decimal(0))
    elif model == 'agency':
        commission_rate = number(x.get('commission_rate'), 'commission_rate', Decimal(0))
        if commission_rate > 1:
            raise ValueError('commission_rate is a decimal in [0,1]')
        revenue = number(x.get('commission_basis'), 'commission_basis', Decimal(0)) * commission_rate
        purchase = Decimal(0)
    else:
        raise ValueError('model must be principal or agency')
    before = revenue - purchase - total_costs
    out = {'status': 'scenario_only', 'currency': currency.upper(),
           'revenue': str(revenue), 'purchase_cost': str(purchase),
           'other_costs': str(total_costs), 'contribution_before_finance': str(before),
           'contribution_after_finance': None, 'funding_capacity': 'unknown',
           'facts_verified': False, 'warnings': []}
    events = x.get('cash_events')
    if events:
        if 'annual_finance_rate' not in x:
            raise ValueError('Explicit annual_finance_rate required with cash events')
        result = cash_model(events, x['annual_finance_rate'])
        after = before - result['finance_cost']
        out.update(finance_cost=str(result['finance_cost']),
                   contribution_after_finance=str(after),
                   peak_funding=str(result['peak_funding']), closing_cash=str(result['closing_cash']),
                   ledger=result['ledger'])
        cash_total = sum((number(e.get('amount'), 'cash amount') for e in events), Decimal(0))
        if abs(cash_total - before) > Decimal('0.01'):
            out['warnings'].append('Cash ledger does not reconcile to pre-finance contribution; check scope and missing payments')
        if result['closing_cash'] < 0:
            out['warnings'].append('Final cash remains negative; settlement/funding unresolved')
        if x.get('funding_limit') is not None:
            limit = number(x['funding_limit'], 'funding_limit', Decimal(0))
            out['funding_capacity'] = 'within_supplied_limit' if result['peak_funding'] <= limit else 'exceeds_supplied_limit'
        if x.get('win_probability') is not None:
            probability = number(x['win_probability'], 'win_probability', Decimal(0))
            if probability > 1:
                raise ValueError('win_probability must be in [0,1]')
            pursuit = number(x.get('pursuit_cost'), 'pursuit_cost', Decimal(0))
            out['expected_contribution_if_inputs_hold'] = str(probability * after - pursuit)
    else:
        out['warnings'].append('No dated cash ledger: financing cost and after-finance contribution unknown')
    out['contribution_margin_before_finance'] = str(before / revenue) if revenue else None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', help='JSON scenario')
    args = ap.parse_args()
    try:
        with open(args.input, encoding='utf-8') as stream:
            print(json.dumps(calculate(json.load(stream)), ensure_ascii=False))
    except (ValueError, TypeError, KeyError) as err:
        print(json.dumps({'status': 'invalid_input', 'error': str(err)}))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
