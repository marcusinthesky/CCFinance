---
type: task
title: Evaluate structured financial news metadata
description: Test joint GLiNER metadata schemas on sampled news and inspect their score distributions.
links: []
status: done
---

# Evaluate structured financial news metadata

## Goal

Implement compact and structured financial-news schemas, preserving the existing
throughput baseline. Inspect source evidence and complete score distributions on
a small reusable sample before selecting enrichment fields for a corpus run.

## Acceptance

- [x] Define typed entities, company attributes, article form and event families.
- [x] Add optional event records and a focused acquisition control.
- [x] Reuse 100 source-verified articles and add explicit diagnostic examples.
- [x] Compare cached small and base models and inspect reviewed failures.
- [x] Preserve reproducible evidence and pass repository and GPU checks.

## Evidence

The [schema](../../../../../infra/inference/gliner_schema.py) keeps the historical
benchmark contract separate from experimental metadata profiles. The
[pilot runner](../../../../../infra/inference/gliner_metadata.py) retains window
boundaries, full classification and company-attribute scores, selected labels,
source offsets and diagnostic expectations. Its checks distinguish structural
validity from semantic accuracy.

The [DVC report](../../../../../data/research/experiments/article-labels/gliner-metadata/report.md)
records eight completed model/profile comparisons. Typed extraction helps
selected person/place cases, but sentiment, local relevance and event factuality
remain unsuitable as research labels. Complete vectors and twenty inspected
examples distinguish score confidence from correctness. The GPU checks and
complete repository quality gates passed.

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
