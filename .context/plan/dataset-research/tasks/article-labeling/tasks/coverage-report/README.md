---
type: task
title: Reconcile filtering and scoring coverage
description: Reconcile filtering and scoring coverage
links: []
status: done
---

# Reconcile filtering and scoring coverage

## Goal

The research agent reports source rows, CPU candidates, duplicate groups,
inference outcomes and eligible company-year coverage separately. Reports retain
publication/capture distinctions and identify every model-generated judgment as
provisional. AI agreement is not human-validated precision or recall.

## Acceptance

- [x] Reconcile CPU counts and exclusion reasons across the complete snapshot.
- [x] Report required throughput and measured native Kev completion estimates.
- [x] Export machine-readable metrics and reusable LaTeX tables.
- [x] Preserve zero-count eligible company-years and explicit coverage limitations.

## Results

The completed CPU census and fixed 1,000-record benchmark each have JSON metrics,
five CSV tables and three LaTeX tables under
`data/research/experiments/article-labels/`. The benchmark report reuses the CPU
census without rescanning the source. Candidate-only company-year cohorts do not
measure usable research coverage; no model-sample results are scaled to cohort
eligibility or claimed annotation accuracy.

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
