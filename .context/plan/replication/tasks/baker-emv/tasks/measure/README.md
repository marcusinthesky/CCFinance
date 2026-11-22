---
type: task
title: Measure article hits and monthly market volatility
description: Reconcile qualifying stories and publisher denominators with VIX and S&P 500 inputs.
links: []
status: done
---

# Measure article hits and monthly market volatility

## Goal

Use DuckDB in `stages/processed/experiments/baker_emv/news.py` for corpus measurement and the raw and processed
market-index commands for external observations. Consume frozen Fine News text and prepared
article dates and canonical flags.

## Acceptance

- [x] Produce one Boolean hit per eligible article requiring economy, equity-market and volatility
  terms. Retain the ID, publisher, publication month and component flags. Reconcile numerator
  and denominator to all eligible captured articles.
- [x] Snapshot dated VIX and S&P 500 closes with provenance and the preceding
  trading close. Build monthly mean VIX and annualized realized volatility from squared
  daily log returns.
- [x] Test phrase variants, repeated hits, zero hits versus absent coverage, and publication
  month differing from capture month. Verify market calculations on a hand-computed example.

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
