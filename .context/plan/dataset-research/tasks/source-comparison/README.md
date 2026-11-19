---
type: task
title: Compare publisher yield across public corpora
description: Prepare a reproducible, bandwidth-conscious publisher-filter comparison.
links: []
status: done
---

# Compare publisher yield across public corpora

## Goal

Implement a small probability-sampled comparison of English publisher retention
across four public corpora. Prepare manifests and transfer estimates before
acquiring article payloads. The
[pipeline guide](../../../../../data/inputs/source-comparison/README.md)
records the design, estimators and limits.

## Acceptance

- [x] Share the publisher filter across the four source projections.
- [x] Prepare pinned file inventories, random group selections and transfer estimates.
- [x] Verify weighting, row-group pruning and the full repository quality gates.
- [x] Document the acquisition commands and limits on population inference.

The DVC lock records the four source samples and their comparison report.

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
