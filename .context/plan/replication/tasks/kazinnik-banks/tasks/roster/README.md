---
type: task
title: Reconcile the historical bank roster
description: Map the published bank universe to dated legal entities and document omitted nodes.
links: []
status: blocked
---

# Reconcile the historical bank roster

## Goal

Reconcile the final article and appendix with the earlier manuscript and its
[earnings-week comparison](https://www.aeaweb.org/conference/2022/preliminary/paper/NfzTsayK).

## Acceptance

- [x] Author a dated crosswalk in `data/inputs/kazinnik-banks/` from the paper’s bank and group
  to supported CCFinance issuers. Record parent, subsidiary, merger and foreign holding-company decisions
  with evidence.
- [x] Distinguish mapped active banks, mapped banks with zero articles, and unresolved banks.
  Publish the denominator for every group; the illustrative 12-bank pilot supplies feasibility
  evidence only.
- [x] Freeze article relevance, week boundaries, January and April monthly windows, and any
  original centrality definitions before comparing them.
- [ ] Verify that the final journal tables and appendix retain the working
  paper's exact roster and week boundaries.

The dated crosswalk, source versions and window rules are in the
[input protocol](../../../../../../../data/inputs/kazinnik-banks/README.md).
The final journal preview confirms the network method, monthly robustness and
Reuters check. Its tables and appendix are unavailable.

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
