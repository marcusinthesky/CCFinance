---
type: task
title: Register and verify the existing body vectors
description: Track existing embeddings and verify source alignment, normalization and restoration.
links: []
status: done
---

# Register and verify the existing body vectors

## Goal

Give the completed `data/processed/embeddinggemma-embeddings/` artifact a DVC owner in place. Use the
existing `infra/inference/` writer and launcher as the production specification.

## Acceptance

- [x] Record the corpus revision, model and image revisions, document prefix, 2,048-token limit,
  768 coordinates and storage type. Reconcile article IDs and row groups to
  the source snapshot.
- [x] Validate has-text flags, vector length, finite values and expected normalization, including the
  zero-vector convention for blank text. Test missing IDs and duplicate IDs on
  small Parquet fixtures.
- [x] Verify DVC status and restoration against recorded hashes separately from local verification.
  Join sample rows by article ID; record encoder revision as provenance. Encoder
  release date imposes no sample restriction.

## Recorded validation

The frozen Fine News revision `3168f32f57107eac95a2c53f024e5e340c91ef2e`
contained 14,807,287 distinct articles across 168 shards and 984 row groups.
The full audit reconciled every ID, position and body flag, and validated the
768-dimensional norms. All bodies contained text. The fixture exercises the
blank-body zero-vector convention. The [launcher](../../../../../../../infra/inference/gemma-run.sh)
pins image `sha256:f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5`.
The audit JSON records the exact model revision, prefix and token limit.

An isolated DVC checkout from the local cache restored all 985 files, including
the writer lock. Each MD5 matched the recorded directory manifest
`68fad30a7cff964595d800d7a7175ff0.dir`. The model stores FP16 coordinates.
The study joins vectors by article ID.

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
