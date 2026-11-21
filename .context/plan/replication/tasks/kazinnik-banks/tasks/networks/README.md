---
type: task
title: Build article–bank pairs and windowed networks
description: Construct unique article–bank pairs, windowed edges and mapped isolates.
links: []
status: done
---

# Build article–bank pairs and windowed networks

## Goal

Use DuckDB to build the study bridge in `stages/processed/experiments/kazinnik_banks.py`; build windowed edges
in `stages/research/experiments/kazinnik_banks.py`. Join dated articles, issuer links and the roster.

## Acceptance

- [x] Retain one row per article and mapped bank with article, publisher and
  mapping evidence. Use eligible publication dates across capture partitions, including articles captured
  in a neighboring month.
- [x] Output bank activity, distinct undirected edges and article-weighted co-mentions by window. Keep
  isolates from the mapped roster and store diagonal article counts separately.
- [x] Test an article naming three banks, one named twice, for exactly three
  unordered pairs of weight one. Check symmetry, no self-links and total weight
  equal to the sum of k(k−1)/2 across articles.

The [results record](../../results.md) includes the production checks for bank
coverage, adjacent captures and the four study windows.

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
