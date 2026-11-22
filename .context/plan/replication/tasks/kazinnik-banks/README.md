---
type: task
title: Replicate bank co-mention networks during early COVID-19
description: Weekly and monthly bank-pair weights, group comparisons and syndication sensitivity.
links: []
status: blocked
---

# Replicate bank co-mention networks during early COVID-19

## Goal

Assess the published bank-network patterns during January and April 2020 using CCFinance
article bodies and all resolved bank mentions. Start from the [authors’ bank-network
study](https://doi.org/10.1016/j.jbankfin.2026.107694).

## Acceptance

- [ ] Freeze the bank universe, article relevance and counting rules against the published
  study.
- [x] Deliver comparable weekly and monthly networks, numerical group comparisons and a syndication
  audit through `report_kazinnik_banks`.

The [CCFinance results](results.md) use the working paper's 34-bank roster and
exact earnings weeks. Verification against the final journal tables and
appendix remains open because the public preview omits those materials.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

| Status | Item | Description |
| --- | --- | --- |
| blocked | [Reconcile the historical bank roster](tasks/roster/README.md) | Map the published bank universe to dated legal entities and document omitted nodes. |

`1 open; 4 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
