---
type: plan
title: Replicate three finance studies with CCFinance
description: Independent DVC targets for aggregate volatility, bank networks and overnight return probes.
links: []
status: blocked
---

# Replicate three finance studies with CCFinance

## Goal

Evaluate what CCFinance preserves about market volatility, bank relationships and firm-level news.
Implement the three paper-specific targets on `feat-replication` through the existing root DVC
pipeline and layer-based Typer CLI. Each study owns its universe. The [feasibility
record](feasibility.md) distinguishes pilot measurements from production acceptance.

The [comparison with the reference papers](comparison.md) reports the final
estimates and uncertainty. All three CCFinance targets ran. The one outstanding
source check is the final journal appendix for the bank roster and windows.

## Delivery

Use one root `dvc.yaml` and the existing raw, processed and research Typer
groups. Keep paper-specific inputs in `data/inputs/<study>/`, processing
artifacts in `data/processed/experiments/<study>/`, and analysis outputs in
`data/research/experiments/<study>/`. Each paper can be reproduced separately.
Freeze external snapshots with retrieval manifests. Keep scientific parameters
under the paper's key in `params.yaml` and declare each stage's inputs,
outputs and Semflow fingerprint. Stages exchange artifact paths across layers.

For each study, exercise the public commands on a small local fixture through
the final table and reconcile it against hand-computed results. Mirror tests
under the Python module that owns the behavior. Distinguish offline fixture
tests, full-corpus validation and a clean reproduction from restored snapshots.
Record the actual commands, data revisions and results when marking work done.

## Acceptance

- [x] Each paper records the source version, selected result, CCFinance substitutions, eligible population
  and exclusions before estimating its final results.
- [x] Each final DVC target rebuilds its tables from recorded inputs in the
  pinned environment. Report null results, material sensitivities and any component the evidence
  cannot support.
- [x] Publish sample attrition, provenance and a trace from each main table to
  its source observations. Validate the new stage fingerprints and run `just check`.

## Reproduction evidence

Two independent workspaces restored the corpus, issuer and article links,
body vectors and external snapshots from the local DVC cache. Both executed
the ten downstream stages in the pinned environment with result reuse
disabled. The ledgers, predictions, tables and figures from all ten output
directories matched byte for byte. See each protocol for tests, sample
attrition and the observation keys underlying its reported estimates.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

| Status | Item | Description |
| --- | --- | --- |
| blocked | [Replicate bank co-mention networks during early COVID-19](tasks/kazinnik-banks/README.md) | Weekly and monthly bank-pair weights, group comparisons and syndication sensitivity. |

`1 open; 2 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
