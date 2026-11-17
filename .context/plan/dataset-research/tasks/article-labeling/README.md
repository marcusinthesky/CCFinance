---
type: task
title: Filter articles and score company coverage
description: Preserve the full CPU selection and measure native Kev company coverage.
links: []
status: done
---

# Filter articles and score company coverage

## Goal

Complete the corpus-wide CPU filter, then size native Kev scoring against
07:00 SAST on 17 November 2026. Preserve source records, all company candidates,
exclusion reasons and unresolved outcomes. AI-only review remains exploratory;
the 95% precision target is not a validated accuracy claim.

The data pipeline agent owns CPU selection, the runtime agent owns native Kev,
and the research agent owns reconciliation and reports. The coordinating agent
owns their contracts, DVC integration and the deadline decision. See the
[labeling guide](../../../../../data/inputs/article-labels/README.md).

## Acceptance

- [x] Materialize and reconcile the complete CPU selection against the frozen source.
- [x] Verify native Kev multi-company inference and measure its completion estimate.
- [x] Preserve resumable scores, uncertainty and an honest completion status.
- [x] Record data dependencies, methods and the required repository checks.

## Results

The complete CPU census reconciles. The fixed 1,000-record benchmark scored 993
records and preserved seven context deferrals without server failures. Its
6.40 successful records/second implies about 22 days for the current broad
selection. No full-corpus GPU run was launched. All scores remain provisional,
and no company pair meets the current 0.95 acceptance policy.

The independent [CPU audit](../../../../../data/research/experiments/article-labels/cpu-audit/report.md)
found generic aliases, publisher-keyword collisions, article furniture and dated
company-name contamination. In the fixed sample, 226 records have completely
observed candidate evidence limited to five generic aliases. See the
[candidate-quality follow-up](../candidate-quality/README.md) before production
scoring. The audit's 25 retained and 20 no-hit reviews are AI observations,
not validated accuracy measurements.

`just check` passed, including 39 tests, Ruff, Pyrefly, Tach, test layout,
Semflow, DVC metadata, document schemas and the LaTeX build. Existing source
comparison results retain their original lock provenance; the new dependency
lock correctly marks those earlier stages stale.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

_No open children._

`0 open; 3 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
