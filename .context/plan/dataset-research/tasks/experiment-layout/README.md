---
type: task
title: Organize experiments and export LaTeX estimates
description: Share experiment contracts, preserve prepared samples and export paper tables.
links: []
status: done
---

# Organize experiments and export LaTeX estimates

## Goal

Organize experiment artifacts and code within their data layers, consolidate
shared contracts and source mappings, and render survey estimates as LaTeX.
Preserve existing preparation without remote source access. See the
[comparison guide](../../../../../data/inputs/source-comparison/README.md).

## Acceptance

- [x] Preserve all prepared file hashes, selections and probabilities after relocation.
- [x] Reuse shared contracts and one source-field registry across the experiment.
- [x] Support configured subsets and statsmodels LaTeX exports with unchanged estimators.
- [x] Verify the full repository gates and compile generated tables with fixture data.

The full `just check` passes, including 28 Python tests. All 25 prepared files
retain their SHA256 hashes, and DVC reports preparation current. An offline
replay from cached metadata reproduces every selection and manifest. All three
LaTeX fragments compile with cached TeX resources and fixture data. No article
payloads were acquired; actual yield reports remain pending acquisition.

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
