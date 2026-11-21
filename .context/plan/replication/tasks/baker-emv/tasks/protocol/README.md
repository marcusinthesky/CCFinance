---
type: task
title: Define the publisher panel and dictionary
description: Freeze publisher identities, matching rules, calibration and six specifications.
links: []
status: done
---

# Define the publisher panel and dictionary

## Goal

Recover the article queries, calibration, missing-source treatment, market transformations and covariance convention
from the [replication files](https://data.mendeley.com/datasets/rmhtcwnvrk/1). Record differences from the original newspaper population.

## Acceptance

- [x] Author the dictionary and hostname-to-publisher mapping in `data/inputs/baker-emv/`. Declare which title and
  body fields are searched and how phrase boundaries, punctuation and repetitions are
  handled.
- [x] Evaluate the four-publisher September 2019–September 2023 candidate window using captured publication days,
  eligible article counts and zero-hit months. Freeze the basket and coverage sensitivity
  before viewing associations.
- [x] Document the six model formulas, available-case rules, intercept and robust inference settings
  against the authors’ code. Specify new calibration dates supported by CCFinance.

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
