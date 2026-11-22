---
type: task
title: Fit rolling reaction and drift probes
description: Fit separate monthly classifiers and retain sample support and convergence diagnostics.
links: []
status: done
---

# Fit rolling reaction and drift probes

## Goal

Implement the scikit-learn probes in `stages/research/experiments/lopez_lira_tang/probes.py`. Verify the executed logic against the
[version-two replication archive](https://data.mendeley.com/datasets/f39x226htv/2).

[Study evidence](../../../../../../../data/inputs/lopez-lira-tang/README.md#rolling-probes-and-portfolios).

## Acceptance

- [x] Use fixed body vectors and separate sign-labelled reaction and drift outcomes. Fit
  monthly using the authors’ six-month window, LBFGS, 10 iterations and seed 42.
  Record class support, feature dimension, parameters, convergence and skipped months.
- [x] Test the authors’ 99 versus 100 training-row boundary, empty test months and
  single-class windows. Confirm every training label was observable before prediction and a
  later price change cannot alter an earlier fit.
- [x] Retain article–security–session predictions and a per-refit audit. Explain any departure from the
  authors’ sample-order or missing-data behavior. Keep the first planned prediction month in
  the audit even if the first fit occurs later.

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
