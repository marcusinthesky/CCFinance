---
type: task
title: Correct dated company identities and generic aliases
description: Repair candidate-generation defects identified by the fixed 1,000-record audit.
links: []
status: in-progress
---

# Correct dated company identities and generic aliases

## Goal

Correct the dated issuer registry and ambiguous lexical aliases before a full
scoring run. Preserve the existing audit and broad candidate output as a baseline.
Evidence lives in `data/research/experiments/article-labels/cpu-audit/`.

The legacy registry pools names across years and chooses an alphabetically first
display name: a 2021 American Airlines match can identify Alpha Metallurgical
Resources. Generic aliases such as `PRICE`, `NEW`, `People`, `NEWS` and `TARGET`
generate millions of overlapping candidates. The legacy cased-name proxy and
unverified publisher ticker annotations also admit false matches.

## Acceptance

- [x] Resolve names, identifiers and memberships for the article date; preserve unresolved links.
- [ ] Define evidence-based restrictions for generic aliases and unverified publisher signals.
- [ ] Compare corrected retrieval with the frozen retained and no-hit audit samples.
- [ ] Measure candidate reduction and missed-company risk before scheduling full scoring.

The completed correction preserves all 12,241,870 retained source records and
38,053,717 candidate links. It aligns resolved names and tickers with verified
dated CIKs, retains original values and explicitly defers unsupported identities.
The 1,934,894 records with title/body name evidence form a diagnostic subset;
they do not replace the broad scoring population or establish retrieval recall.

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
