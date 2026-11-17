---
type: task
title: Complete corpus article tags and company scores
description: Correct candidate identities, evaluate decisions and complete the full article-scoring workload.
links: []
status: in-progress
---

# Complete corpus article tags and company scores

## Goal

Complete the full corpus labeling objective following the fixed 1,000-record
pilot. Preserve all qualifying articles and company links; diagnostic evidence
tiers and runtime limits must not silently redefine the dataset population.
The recorded working deadline is 07:00 SAST on 17 November 2026, pending
clarification of the goal text's October date.

The candidate agent corrects dated identities and lexical evidence. The runtime
agent evaluates decision questions and bounded GPU batching. The scoring agent
owns portable, resumable production execution. The coordinator owns DVC,
reconciliation, quality gates and delivery.

## Acceptance

- [x] Correct and reconcile candidate identities across the complete source population.
- [x] Evaluate native decisions against preserved examples and independent audit cases.
- [ ] Materialize article tags and company scores for the full qualifying population.
- [ ] Preserve source memberships, unresolved evidence and explicit processing failures.
- [ ] Verify completion counts, provenance, reproducibility and repository quality gates.

The corrected fixed pilot processed 1,000 records: 993 scored, seven deferred by
the context limit, and one transient timeout recovered on resume. Its 3,137
candidate pairs include 24 provisional accepted pairs across 21 articles and
105 unresolved identities. These outcomes are model suggestions, not validated
research labels. Local inference remains far below the throughput required for
the complete 12.24-million-record population by the working deadline.

The [accepted-pair source review](../../../../../data/research/experiments/article-labels/accepted-pilot-audit/report.md)
found developed company coverage in all 24 links, with separate editorial-format
questions. It is an AI-assisted, post-selection check without validated precision
or recall. The initial full-run checkpoint preserved 1,598 source records and
4,024 candidate links without metadata loss; its sparse-index storage defect and
original implementation are archived before restarting production.

Observed company-year and consecutive-year panels now distinguish committed
model selections from CPU candidates, pending records and unscorable links.
The [context audit](../../../../../data/research/experiments/article-labels/context-audit/report.md)
preserves the seven deferred transcripts and the model's documented length
limits. These reports do not complete the unprocessed population or establish
human-validated research quality.

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
