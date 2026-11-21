---
type: task
title: Estimate and report the six monthly models
description: Produce regression tables and tracking figures with coverage sensitivities.
links: []
status: done
---

# Estimate and report the six monthly models

## Goal

Use `stages/research/experiments/baker_emv.py` for `build-baker-emv-panel` and `report-baker-emv`. Join the scaled tracker to market
observations by month.

The archived Table 1 specification uses an intercept in each column. The VIX
columns use current EMV, then add its first two lags, then add lagged VIX.
The log column regresses log VIX on log EMV. The realized-volatility columns
use current EMV alone and with lagged realized volatility. The archive
exports standard errors from Newey-West regressions with two lags.

## Acceptance

- [x] Apply the frozen source scales, average and final rescaling. Test a small
  panel with unequal publisher variance, a missing month and a zero-variance source.
  Record the treatment of each.
- [x] Fit the six predeclared statsmodels OLS specifications. Validate one column against an
  independent calculation on identical rows, checking coefficients, standard errors, observation count and
  fit with stated tolerances.
- [x] Produce the six-column table, tracking figures, source coverage and sensitivity results. Retain
  each model’s inclusion flags, especially for logs and lags; interpret the contemporaneous
  associations.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

_No open children._

`0 open; 0 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
