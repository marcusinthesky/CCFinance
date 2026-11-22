---
type: task
title: Construct portfolios and report supported results
description: Measure portfolio-day hit rates, returns and leg support from saved predictions.
links: []
status: done
---

# Construct portfolios and report supported results

## Goal

Use saved predictions to reproduce the daily leg construction. Report the information
in the initial reaction separately from subsequent drift.

[Study evidence](../../../../../../../data/inputs/lopez-lira-tang/README.md#executed-results).

## Acceptance

- [x] Specify which story supplies the score when a security has multiple articles
  in a session. Count each security once, retain predicted signs and require
  at least two positions of a sign for its leg to contribute.
- [x] Test single-position zeroing, one active leg, two active legs and days with
  no predictions. Reproduce the authors’ evaluated-day denominator, positive-portfolio-day hit rate, mean return
  and drift Sharpe on a small independent fixture.
- [x] Publish monthly model support, portfolio-day positions and exposures, and separate reaction and
  drift tables. Report how many sessions have both legs, convergence warnings, body-vector
  reuse and limits of the public-data sample. A weak or null result
  is reportable.

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
