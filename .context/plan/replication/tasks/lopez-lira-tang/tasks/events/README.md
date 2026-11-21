---
type: task
title: Establish timed articles and eligible issuers
description: Recover publication evidence and define issuer, session and novelty eligibility.
links: []
status: done
---

# Establish timed articles and eligible issuers

## Goal

Build reusable timestamp evidence in `stages/processed/publication_times.py`. Apply overnight, issuer-focus and repeat-event rules
in the study sample. Begin with the two audited publisher formats; track
any expansion by publisher.

[Study evidence](../../../../../../../data/inputs/lopez-lira-tang/README.md#event-eligibility).

## Acceptance

- [x] Retain explicit first-publication evidence, timezone, UTC capture instant and parser version. Require
  publication after the previous session close and before 09:00 New York time,
  with this body captured by the cutoff.
- [x] Start from historically eligible US common stocks or declare a coverage-based subset
  using pre-period data. Preserve issuer–security mappings, delistings, ambiguous classes, unknown start dates
  and exclusion reasons.
- [x] Record complete-article eligibility, body-focus evidence, price-movement-only exclusions and repeat-event policy. Quantify the
  gap between public proxies and RavenPack relevance and 90-day event novelty; audit
  multi-issuer bodies.
- [x] Test DST, a Friday before a Monday holiday, early closes, exact cutoff,
  an updated page and capture before purported publication. Preserve the captured text
  version and original article ID.

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
