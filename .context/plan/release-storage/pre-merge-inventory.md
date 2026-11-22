# Pre-merge storage inventory

On 22 November 2026 the configured `hf-bucket` remote contained 10,906
content-addressed objects beneath its DVC prefix. Comparing current-branch
outputs and the children of their directory manifests found 7,745 of 8,413
unique push-eligible objects present. At that point 668 objects totaling
6,082,095,731 bytes remained absent, including 5,744,990,108 bytes for the
body-embedding stage. An independently started `dvc push` was holding the
repository lock during the inventory. These counts describe that observation,
not the final backup state.

All 170 objects for the frozen Fine News directory were already present in the
bucket, including the 168 source shards. Its current `push: false` setting
excludes the snapshot from new pushes. It leaves earlier uploads accessible
according to the bucket's visibility, which the Hub reported as public. The
owner requested that visibility remain public temporarily. The 570 identified
objects for excluded embedding experiments were absent. The difference between
the total remote object count and the current branch's reachable set cannot
establish which objects are safe to remove.

## First benchmark candidates

| Artifact | Current measurement | Comparison to run after release |
| --- | --- | --- |
| Body embeddings | Approximately 22 GiB in processed storage, with 768 FP16 coordinates per capture | Compare FP16 byte-stream split and Zstandard with the production encoding. Measure both projected scans and random reads of the same IDs. |
| GLiNER extraction | Approximately 11 GiB in processed storage | Compare nested article-level and occurrence-level layouts, including the cost of materializing offsets and scores for a single issuer. |
| Company links | Approximately 5.1 GiB in processed storage | Measure repeated identifiers and surfaces, and test a normalized representation against the current candidate and evidence arrays. |
| Public Parquet release | 190 shards, 31,542,642,813 bytes, including 19,285,178,454 compressed embedding-column bytes | Use as a measured comparison for serialization. Some DVC consumers require surface text or numeric scores absent from smaller projections. Validate each consumer before replacing its input. |

The public export reproduced 14,807,287 distinct captures, 5,220,290 usable
linked captures and 2,547,597 usable captures with a three-mention link. The
full release retains 386,352,022 extracted occurrences, 158,582,914
mention-link records and 16,828,111 article–issuer pairs before screening.
