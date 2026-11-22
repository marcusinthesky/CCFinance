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
