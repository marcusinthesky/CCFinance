---
type: task
title: Choose and evaluate the company-focus rule
description: A company-focus rule chosen on development articles and scored on test articles.
links: []
status: done
---

# Choose and evaluate the company-focus rule

## Goal

Separate issuers an article is about from passing mentions, using the existing
seed-43 model-adjudicated roles rather than new labels.

## Acceptance

- [x] Choose the rule on development articles: at least three mentions, with F1 0.717.
- [x] Score it end to end on test articles: precision 0.661, recall 0.569.

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
