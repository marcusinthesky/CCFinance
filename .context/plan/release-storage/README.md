---
type: plan
title: Migrate archive storage and retire superseded DVC objects
description: Migrate archive storage and retire superseded DVC objects
links: []
status: backlog
---

# Migrate archive storage and retire superseded DVC objects

## Goal

Reduce the bytes required to restore the published analysis while preserving the
record-level meaning of each retained artifact. Use the completed frozen
outputs as inputs to serialization changes. Begin the migration after the
public metadata release has a verified, citable Hub revision.
The [pre-merge inventory](pre-merge-inventory.md) records the starting
object counts and sizes and identifies the first benchmark candidates.

## Execution order

1. **Inventory.** Walk the DVC locks and standalone pointers at each retained
   release, branch, tag and experiment. Expand directory manifests to child
   hashes, deduplicate shared objects, and record on-disk and remote bytes.
   Identify inputs with restricted rights, intermediate data still consumed by
   a stage, and expensive outputs whose measurements cannot be recovered cheaply.
   Check the other repositories and clones sharing this remote before deriving
   a deletion set. Record the public Hub release independently.
2. **Benchmark.** On matched samples of each major artifact family, compare
   size, projected reads, full scans and random lookups. For embeddings,
   preserve the existing FP16 bit patterns and benchmark realistic 768-coordinate
   batches. For spans and links, measure repeated IDs and strings, bounded
   integer widths, nested encodings and compression. Report measured savings
   net of data already deduplicated by DVC.
3. **Migrate.** Update the production writer and readers together, and transcode
   a side-by-side copy of the existing artifact. Verify keyed equality, row
   ordering where contractual, schema, nulls, offsets, nested values, vector
   bits and downstream paper totals. Record old and new hashes and the tool
   versions. Allow DVC to calculate hashes from the files with targeted
   stage commits. Review affected downstream input hashes individually and
   verify compatibility before recording an existing downstream output as
   current. Keep changes to labels, numerical precision or sample selection
   as separate scientific revisions.
4. **Merge and restore.** Squash-merge the reviewed change into main when
   authorized. Tag the intended release, push its required DVC objects to the
   intended private backup, then restore from an empty cache and reproduce
   the paper counts. Record an alternate restore path for each intentionally
   excluded output. Preserve a private recovery copy of any history or
   artifacts required for rollback.
5. **Prune.** After merge and restore, calculate the exact remote object keys
   outside the retained set, including hashes reachable only via directory
   manifests. Review the key count and total bytes, destination and retained
   revisions with the owner before deleting anything. Recheck reachability
   immediately before deletion and repeat the clean restore afterwards.
   A currently tracked intermediate can be retired only after explicitly
   changing its stage contract and the restore requirements.
6. **Decide on public Git history.** A squash merge adds a commit to main's
   existing history. A separate clean public repository can start from the
   verified tree while the original repository remains a private archive.
   Replacing main in place would invalidate commit links and require coordination
   with collaborators and branch protection. Select the public lineage before
   finalizing the remote retention list. Any history replacement requires
   separate owner approval and a tested Git bundle.

## Acceptance

### Release and storage measurements

The `ccfinance-v1` release pairs Git commit
`b79d2943a55d264f5c74b9697e71068e0c3fecbc` with public Hub revision
`524d04acec2ed7dfc5b76cfb09fae9e57850b062`. The original private DVC
prefix held 10,906 objects totaling 60,291,018,381 logical bytes.

| Artifact | Measurement and disposition |
| --- | --- |
| Fine News | The 168 restored shards and original provenance file reproduce `3cd438d50a74f30d54d6eb854642e69b.dir`. Use `just restore-source` with staging access. |
| EmbeddingGemma | `just restore-vectors` recreates the original 984 Parquet files from the public release. It checks each file against the Git-tracked group manifest. The expected output directory is `68fad30a7cff964595d800d7a7175ff0.dir`, including its empty lock file. |
| GLiNER | The original DuckDB output uses Zstandard. On five files selected at size deciles 1, 3, 5, 7 and 9, level 12 with 32,768-row groups saved 1.9% on mentions. We kept the existing frozen extraction. |
| Issuer links | DuckDB Zstandard level 12 with the production row-group setting reduced the complete output from 5,374,769,724 to 4,960,068,281 bytes. All 2,954 files were accounted for, with ordered Arrow values and schemas checked for every Parquet file. The original directory was `aa8f98149cc5143d3e14dbf37bb6e0ab.dir`. The migrated directory is `366a576a401392ab41ca63a29527c550.dir`. |

The migrated pipeline requires 7,428 push-eligible objects totaling
16,812,460,163 bytes. Keeping the original release recoverable adds the
earlier link objects. Together the two releases reference 10,382 objects
and 22,187,562,408 bytes in the private release prefix. These figures measure
logical file sizes. The storage provider may deduplicate their underlying bytes.

For the original Git release, use the two Hub restore commands from the
migration revision with explicit paths into the historical checkout. Select
`s3://CCFinance/dvc-release-v1` for its remaining paper outputs. Historical
objects used exclusively by earlier development versions are inventoried under
`dvc-store/`. The private `recovery/ccfinance-v1/` directory contains the Git
bundle and the compressed data archive for `embedding-studies-v1`.

- [ ] Measured savings and logical equivalence are recorded by artifact family.
- [ ] The tagged release restores from an empty cache and reproduces the article,
  issuer and embedding checks without another inference run.
- [ ] The owner approves an enumerated deletion set after the merge, and a
  post-prune restore confirms that all retained revisions remain usable.

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
