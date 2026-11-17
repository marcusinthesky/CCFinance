---
type: task
title: Materialize the full CPU article filter
description: Materialize the full CPU article filter
links: []
status: done
---

# Materialize the full CPU article filter

## Goal

The data pipeline agent verifies the existing Rust Aho–Corasick artifacts,
materializes source-linked selections and preserves all exclusions and evidence.
Unchanged matching may be reused only when source and prediction hashes match.

## Acceptance

- [x] Verify all 168 source shards and adopted prediction chunks.
- [x] Reconcile retained and excluded indexes with every source record.
- [x] Preserve duplicate memberships, candidate evidence and date uncertainty.
- [x] Report actual retained documents and the remaining inference workload.

## Results

The verified prior Rust run was adopted without rematching. All 14,807,287 source
records reconcile: 12,241,870 retained and 2,565,417 without a candidate. Building
the compact indexes took 374.64 seconds. Retained records contain 11,984,483
exact-text groups and 38,053,717 candidate pairs. Candidate quality remains
unvalidated; the independent audit identifies generic aliases and dated registry
identity errors before production scoring.

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
