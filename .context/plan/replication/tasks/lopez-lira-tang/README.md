---
type: task
title: Replicate rolling return probes with article bodies
description: A timed article–security panel, rolling fits and daily reaction and drift portfolios.
links: []
status: done
---

# Replicate rolling return probes with article bodies

## Goal

Test the overnight embedding component of [Lopez-Lira and Tang](https://arxiv.org/html/2304.07619v6) using CCFinance’s fixed
EmbeddingGemma article-body vectors. Preserve the rolling supervised task and disclose the change
of text and encoder.

[Study methods and executed results](../../../../../data/inputs/lopez-lira-tang/README.md).

## Acceptance

- [x] Document the security universe, timing, relevance and event-novelty evidence and their limits.
- [x] Deliver rolling predictions, skipped fits, portfolio-leg support, reaction and drift metrics and
  sample attrition through `report_lopez_portfolios`.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

_No open children._

`0 open; 5 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
