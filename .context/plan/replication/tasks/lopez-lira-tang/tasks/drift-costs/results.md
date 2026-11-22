---
title: Drift after execution costs on the fixed overnight sample
description: Daily portfolio means for five one-way execution costs on the 277 evaluated sessions.
---

# Drift after execution costs

All three portfolios require an execution rebate to break even. At a one-way
cost of 5 basis points, mean daily drift ranges from −11.07 to −17.23 bp.

| Representation | Evaluated zero-leg days | Mean active legs | Gross (0 bp) | 1 bp | 5 bp | 10 bp | 25 bp | Break-even one-way cost (bp) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma body | 123 | 0.708 | −10.15 | −11.57 | −17.23 | −24.30 | −45.53 | −7.17 |
| Gemma title | 124 | 0.664 | −4.43 | −5.76 | −11.07 | −17.72 | −37.64 | −3.33 |
| MiniLM title | 125 | 0.671 | −4.69 | −6.03 | −11.40 | −18.12 | −38.26 | −3.49 |

Scenario columns give mean net daily drift in basis points per unit of strategy
capital. A qualifying equal-weighted long or short leg trades one unit of entry
notional, split across its securities. Each leg pays the assumed rate twice on
that fixed notional, once at entry and once at exit. Two active legs therefore
cost four times the quoted one-way rate. The scenarios exclude borrow charges.

Each mean includes all 277 evaluated days, with zero cost and zero return on
zero-leg days. The zero-cost calculation reproduces the three saved portfolio
means to within 0.0000000001 bp. Break-even divides the gross mean by twice
the mean active legs. Reproduce with `just dvc repro report_lopez_drift_costs`.
