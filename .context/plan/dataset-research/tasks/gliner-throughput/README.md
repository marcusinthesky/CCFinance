---
type: task
title: Benchmark local company extraction
description: Measure full-article GLiNER extraction speed and output stability on the local GPU.
links: []
status: done
---

# Benchmark local company extraction

## Goal

Assess whether local extraction can process 12 million articles in 24 hours
(138.9 articles/second), or the current 12,241,870 retained rows at 141.7/second.
Measure company spans, per-mention roles and article type together, preserving
long-document coverage. Treat output stability and reviewed accuracy separately.

## Acceptance

- [x] Stop native Kev serving while preserving completed scores and checkpoints.
- [x] Prepare a source-verified 10,000-row sample and the existing 1,000-row pilot.
- [x] Verify CUDA execution and compare precision, attention and batching paths.
- [x] Repeat the best configuration on the full sample and record runtime limits.
- [x] Preserve DVC evidence, document quality limits and pass repository checks.

## Evidence

The [inference tools](../../../../../infra/inference/README.md) pin model and
library versions, preserve explicit source-offset corrections, and separate
initialization from steady-state timing. The benchmark remains experimental;
company identity linking and human validation are required before dataset use.

The selected 74M checkpoint achieved 162.3–163.7 records/second across three
10,000-record runs, projecting 20.9 hours of extraction for the retained
population. It uses FP16, DisentangledFlash, compiled extraction heads, buffered
worker preprocessing and batched role scoring, preserving the original window
coverage. All records passed structural checks. The
[DVC benchmark report](../../../../../data/research/experiments/article-labels/gliner-benchmark/report.md)
records numerical differences and known semantic limitations. The complete
repository check passed, including 47 tests; GPU parity and reinstall checks
passed separately.

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
