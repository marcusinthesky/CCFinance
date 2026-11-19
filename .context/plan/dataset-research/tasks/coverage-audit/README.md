---
type: task
title: Audit staging coverage and quality
description: Measure usable, company-focused coverage per listed issuer-year against the Pricing Perspective screen.
links: []
status: in-progress
---

# Audit staging coverage and quality

## Goal

Evaluate staging coverage and quality against the
[dataset requirements](../dataset-requirements/README.md). Measure usable and
company-focused articles per listed issuer and year, with zero counts, the
Pricing Perspective screen and measurement quality. The
[pipeline guide](../../../../../data/inputs/coverage/README.md) records the
definitions and limits.

## Acceptance

- [x] Date-check and deduplicate every article.
- [ ] Add a public issuer-size measure.
- [x] Choose and evaluate a company-focus rule without new labels.
- [ ] Build the firm-year panel over an evidenced universe.
- [ ] Report coverage, the Pricing Perspective screen and candidate release targets.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

| Status | Item | Description |
| --- | --- | --- |
| in-progress | [Build the firm-year coverage panel](tasks/coverage-panel/README.md) | Raw, dated, usable and focused article counts per listed issuer and year. |
| in-progress | [Report coverage, the PP screen and release targets](tasks/coverage-report/README.md) | Coverage tables, pgfplots figures and a rendered report with release-target candidates. |
| in-progress | [Snapshot SEC public float for issuer size](tasks/firm-size/README.md) | SEC public float by filer and measurement date. |

`3 open; 2 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
