# Economics input
Use one currency and one quantity/unit basis per scenario. Quotes must be normalized before calculation. Supply rates as decimals: 0.12 means 12%. All cash amounts use sale currency; cash inflows positive and outflows negative.

Principal JSON: model, currency, quantity, unit, purchase_unit, sale_unit, costs [{name, amount, basis}], cash_events [{day, amount}], annual_finance_rate, optional funding_limit, optional win_probability and pursuit_cost.
Agency JSON: model=agency, currency, commission_basis, commission_rate, costs and optional cash events/finance inputs.

Each cost amount is a total, not a per-unit amount. costs exclude the financing calculated by the ledger. Record whether freight/duty is already included in purchase/sale terms to avoid double counting. Preserve evidence separately in the dossier.

Ledger assumptions: events are grouped by integer day; opening cash is zero; simple Actual/365 interest accrues on a negative balance between event days and is charged at the next event before that day's flows; no positive-balance interest. Final negative balance is unresolved funding, not a completed sale. No projection beyond the last event.

Peak exposure includes accrued financing under this model. A missing ledger means financing and final profit after financing remain unknown; output pre-finance contribution only. A missing funding limit means capacity unknown, never “finance approved”.

Optional expected value equals supplied probability times after-finance contribution minus separate pursuit cost. Do not use it unless the probability and pursuit basis are documented, and do not count pursuit cost twice. This helper is a scenario calculator, not a pricing, tax, credit or legal engine.
