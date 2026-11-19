---
type: task
title: Date-check and deduplicate articles
description: Date status, residual duplicates and usability for every article.
links: []
status: done
---

# Date-check and deduplicate articles

## Goal

Flag publication dates that the capture does not support, and residual
duplicates, while keeping every source record.

## Acceptance

- [x] Classify each date as consistent, archival, future or missing from its capture lag.
- [x] Mark the earliest of exact-text and normalized-URL repeats canonical.
- [x] Run on all 14.8M articles: 11.26M usable, 3.46M archival, 312k text and 24k URL repeats.

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
