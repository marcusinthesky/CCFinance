---
type: task
title: Compare Stanza and GLiNER on financial company mentions
description: Compare Stanza and GLiNER on financial company mentions
links: []
status: done
---

# Compare Stanza and GLiNER on financial company mentions

## Goal

Compare Stanza and GLiNER on financial company mentions

## Acceptance

- [x] Freeze the 250 passages and blind reference spans specified in the [exercise](../../tasks1/stanza-microbench.md).
- [x] Run both pinned extractors and record paired exact-span scores, uncertainty and representative errors with the reproducible scoring command.
- [x] Identify the published all-class reference scores and explain the economic consequence of a missed co-mention.

## Evidence

The [benchmark record](../../../../../data/inputs/stanza-microbench/README.md)
links the frozen manifest, annotation instructions, gold spans, predictions,
scoring command, results and co-mention examples.

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
