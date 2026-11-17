---
type: plan
title: CCFinance dataset research
description: Assess feasibility and define a research-ready financial news dataset.
links: []
status: in-progress
---

# CCFinance dataset research

## Goal

Assess the staging corpus and define a reproducible financial news dataset for
company-level language and market research.

## Acceptance

- [ ] Evaluate staging coverage and quality against the dataset requirements.
- [ ] Establish evidence-based release targets and a plan for meeting them.

<!-- insitu:begin sql
id = "planning-children"
model = "children"
template = "children.md.j2"
-->

| Status | Item | Description |
| --- | --- | --- |
| in-progress | [Correct dated company identities and generic aliases](tasks/candidate-quality/README.md) | Repair candidate-generation defects identified by the fixed 1,000-record audit. |
| in-progress | [Complete corpus article tags and company scores](tasks/complete-article-labels/README.md) | Correct candidate identities, evaluate decisions and complete the full article-scoring workload. |
| backlog | [Define dataset requirements](tasks/dataset-requirements/README.md) | Establish and validate the functional requirements for research use. |

`3 open; 5 terminal`

<!-- insitu:end -->

## Backlinks

<!-- insitu:begin sql
id = "reference-backlinks"
model = "backlinks"
template = "backlinks.md.j2"
-->

_No declared backlinks._

<!-- insitu:end -->
