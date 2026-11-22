---
type: task
title: Measure publisher influence during the volatility shock
description: Measure publisher influence during the volatility shock
links: []
status: done
---

# Measure publisher influence during the volatility shock

## Goal

Identify which publishers account for sensitivity to March and April 2020.

[Publisher exclusions, estimates and verification](results.md).

## Acceptance

- [x] Rebuild the EMV tracker four times, omitting one publisher at a time and recalibrating on the original calibration dates.
- [x] Deliver a table of VIX and realized-volatility R² gaps against the archived tracker, for the full 49 months and the 47 months excluding March and April 2020.
- [x] Verify that including all publishers reproduces the frozen benchmarks. Report missing cells and treat these comparisons as exploratory.

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
