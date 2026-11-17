# Article labels and research filters

This experiment separates company retrieval, dated issuer identity and model
judgments about article coverage. Its source is the restored
[Fine News snapshot](../fine-news/README.md). The historical 115-domain allowlist
is an acquisition policy; it has not been reviewed as a trusted-publisher list.
All model labels remain provisional pending human evaluation.

## Source and CPU evidence

The adopted Rust Aho–Corasick run covers the same 168 source files. Source and
prediction checksums are verified before adoption. The compact CPU index retains
12,241,870 of 14,807,287 source records and accounts separately for every exclusion.
Article keys use relative source paths and physical row numbers. Native article
IDs are preserved but are not assumed unique.

Text remains in the raw snapshot. Indexes store coordinates, text hashes,
candidates and matching evidence. Exact-text groups retain every source membership;
they do not establish complete syndicated-story deduplication. A literal name or
publisher keyword match establishes a retrieval candidate, not company relevance.

The independent [CPU audit](../../research/experiments/article-labels/cpu-audit/report.md)
confirmed correct stored offsets but found generic aliases, footer mentions,
non-financial publisher tags and a cross-year issuer-name defect. The review is
qualitative AI evidence, not human gold or measured population precision/recall.
Its retained and no-hit source samples, observations and checksums are preserved.

## Dated candidate correction

`correct_article_candidates` preserves every broad candidate and source record.
It uses a unique verified article-year issuer link to resolve Top1000 names,
tickers and CIKs together. Ambiguous or unsupported links remain unresolved;
scoring never substitutes the original, potentially wrong company name.

The corrected index records original values, authority identifiers, supported
aliases, lexical ambiguity and evidence tiers. The SEC snapshot contains 190
cached submissions records. Current registry names are not certified historical
names, and SEC former-name filing dates are not guaranteed validity intervals.
Undated GH identities retain their limitation. Publisher tags and legacy ticker
spans remain unverified retrieval evidence.

Title/body evidence tiers are retrieval diagnostics. They do not classify primary
coverage or remove candidates from the scoring population. Capped stored spans
remain censored evidence rather than proof that other mentions are absent.

## Fixed pilot

The pilot selects 1,000 retained source records by the smallest
`SHA256(seed:article_id)` values before loading bodies or requesting predictions.
Duplicate source copies remain in this sampling frame. `selection.parquet`
preserves the sample; it cannot establish missed-company recall from survivors.

The frozen initial pilot lives in
`data/processed/experiments/article-labels/benchmark-1000/`. It scored 993 records,
deferred seven beyond 8,192 tokens and had no server failures. Its original rubric
accepted no pairs at 0.95. Exact scorer, reporter, parameters and runtime assets
are archived alongside DVC pointers; frozen stages preserve that baseline.

Verify the completed corrected pilot and its report with:

```bash
just dvc repro benchmark_company_labels
just dvc repro report_company_benchmark
```

Outputs use `benchmark-corrected-1000/` beneath the processed and research
experiment directories. `benchmark.json` records counts and measured throughput;
`decisions.jsonl` and `predictions.parquet` preserve the small pilot's predictions.
Fresh source-only audit labels are sealed before model outputs are inspected.
Neither synthetic examples nor AI agreement establish human-validated accuracy.
Both completed pilots are frozen. A new experiment requires its own output path
and an unfrozen stage, preserving the existing manifests and implementation hashes.

The corrected pilot scored 993 records and deferred seven by context length.
One transient timeout succeeded on resume. At the fixed cutoff, 24 candidate
pairs across 21 records were provisionally accepted; 105 pairs had unresolved
identities. The cumulative clock includes an unusual stall and sparse source
reads. Its conditional linear runtime projection is not a reliable dense-corpus
completion date. `row_groups_read` and `last_source` describe the latest
invocation; completion counts and elapsed time accumulate across resumes.

The [accepted-pair source review](../../research/experiments/article-labels/accepted-pilot-audit/report.md)
examines all 24 accepted links against the 21 original articles. It found developed
company coverage, including a syndicated issuer release and a promotional roundup
that require separate source-format treatment. This AI-assisted, post-selection
review does not measure population precision or missed-company recall.

The [context audit](../../research/experiments/article-labels/context-audit/report.md)
records the seven deferred transcripts and their verified source evidence. Raising
the admission limit alone would not establish reliable long-document predictions.

## Company decisions

The selected rubric asks three binary questions per resolved company, using its
canonical name and tickers: whether the article mentions it, provides meaningful
company-specific information beyond a mention, and treats it as a main subject.
Several companies may be primary. The manifest records the exact question
templates and article-kind criteria. The current runtime is Kev-4B in BF16.
Production uses the separate `kev-4b-low-memory.json` profile. It retains the
same model and 8,192-token admission while reducing GPU graph buffers. A fixed
16-request parity check preserved all tested 0.5 and 0.95 threshold decisions;
the original corrected pilot retains its original runtime profile.

`identity_score`, `substantive_score` and `raw_primary_score` preserve independent
model outputs. `coverage_score` is their substantive/primary maximum: a ranking
rule rather than a calibrated union probability. Contradictory marginals retain
consistency flags. `primary_score` is available only after identity meets the
configured cutoff. A provisional accepted pair requires confident identity and
coverage without a strong coverage contradiction. Article kind does not gate it.
Saved outputs support later threshold comparisons without rerunning inference.

## Native inference and checkpoints

[Native Kev](../../../infra/inference/README.md) runs in a separate pinned GPU
runtime. Pydantic's System One client shares each article across company questions
in one request. Exact repeated company descriptors share questions while retaining
all namespace-specific links. Large candidate sets use bounded requests.
Article kind is an annotation, rather than an automatic editorial-content gate.

The runtime profile records model revisions, checkpoint hashes, precision,
kernels and context admission. Oversized documents are explicitly deferred;
silent text truncation is disabled. Prediction manifests preserve the scorer and
runtime contract. A changed scientific contract requires a new output directory.
Operational deadlines, transport timeouts and concurrency can change on resume.
Pass `--source data/raw/fine-news` to override archived absolute source locations.

```bash
just dvc repro score_company_labels
```

Production stores compressed source-record Parquet chunks and a small SQLite
resume ledger in `data/processed/experiments/article-labels/corpus/`. It preserves
source metadata, candidate provenance and raw model outputs. Successful identical
requests can be reused; transient server failures are retried on resume. Context
failures, unresolved identities and pending records stay separate from negatives.
`progress.json` reports counts and `storage.json` gives a conditional disk estimate.

The first production attempt stopped after 1,598 records because temporary JSON
payloads left sparse SQLite pages after export. That attempt and its implementation
are preserved under `corpus-pre-storage-fix/` and the scorer archive. Production
checkpoints now replace exported request payloads with compact lookup records in
one transaction; the disk estimate still accounts for allocated pages.

An incomplete, storage-limited or deadline-limited run exits unsuccessfully after
saving checkpoints. DVC therefore does not proceed automatically to its report.
To inspect a partial run, invoke the reporting command directly:

```bash
env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV \
  uv run --project src/python --offline --frozen --package ccfinance-pipeline \
  pipeline stages research report-article-labels \
  --cpu data/processed/experiments/article-labels/cpu \
  --census data/research/experiments/article-labels/cpu \
  --scores data/processed/experiments/article-labels/corpus \
  --output data/research/experiments/article-labels/corpus-progress
```

Choose a new output directory for each snapshot; reporting refuses to overwrite
an existing report. The DVC-owned `corpus/` report is reserved for a completed run.

After a production resume, reports use `progress.json` when it differs from the
previous `summary.json`. Matching terminal snapshots retain the summary. Counts,
status and timing always come from one metadata snapshot.

Reports distinguish source records, candidate pairs, scored coverage and pending
work. They provide CSV and LaTeX tables without projecting accepted model labels
as validated population coverage. The 0.95 cutoff is a provisional selection rule,
not an empirical accuracy guarantee. Parameters and the operating deadline live
under `experiments.article_labels` in `params.yaml`; measured end-to-end capacity
must support any claim that full scoring will finish before that deadline.

Production reports add `observed_company_year.csv` and `observed_cohorts.csv`.
The existing `company_year.csv` and `cohorts.csv` retain CPU candidate counts.
Observed panels count stored accepted selections; substantive and primary counts
add the respective score cutoff. Independent scores need not produce nested
counts. Source copies and exact-text documents remain separate, with explicit
pending, review and unscorable records. Unrostered namespaces and unknown years
retain NULL candidate denominators and do not enter membership cohorts. These
are provisional selections in committed checkpoints, without population scaling
or validated usable-article claims.
