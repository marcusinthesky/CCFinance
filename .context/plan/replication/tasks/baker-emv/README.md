---
type: task
title: Replicate monthly news-based volatility tracking
description: A monthly publisher panel, normalized EMV tracker and six volatility regressions.
links: []
status: done
---

# Replicate monthly news-based volatility tracking

## Goal

Test whether the monthly CCFinance equity-market-volatility (EMV) index tracks VIX and realized
S&P 500 volatility. Use the six monthly specifications from the [authors’ study](https://www.nber.org/papers/w25720).

## Acceptance

- [x] Freeze a publisher panel and version the matching and normalization rules.
- [x] Deliver the publisher-month ledger, monthly analysis panel, six regression columns and tracking
  figures through `report_baker_emv`.

The [study protocol](../../../../../data/inputs/baker-emv/README.md) records coverage,
archive validation and the fitted results.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

_No open children._

`0 open; 4 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
