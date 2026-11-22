---
type: task
title: Build dated prices and the estimation sample
description: Reconcile security identities, corporate actions, market sessions and sample attrition.
links: []
status: done
---

# Build dated prices and the estimation sample

## Goal

From timed events create a security/date request manifest. Snapshot daily bars and
corporate actions, then prepare a join to the previous close, session open
and close. Keep failed requests in the ledger.

[Study evidence](../../../../../../../data/inputs/lopez-lira-tang/README.md#prices-and-return-definitions).

## Acceptance

- [x] Record retrieval vintage, symbol history, venue and adjustment convention. Test a split,
  ex-dividend session, ticker change, missing bar and delisted security; reconcile examples with
  issuer or exchange records.
- [x] Construct separate close-to-open reaction and open-to-close drift labels following the authors’ total-return
  treatment. Test exact zero and both signs on hand-computed cases and prevent
  double split adjustment.
- [x] Join body vectors and prices by article, security and session. Publish per-filter
  losses, multi-issuer counts, unique firms per day including empty days, and six-month
  training counts. Freeze eligibility before measuring performance.

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
