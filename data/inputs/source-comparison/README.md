# Source comparison

This pilot estimates how many English source records the historical Fine News
publisher allowlist (115 domains, including subdomains) retains in Fine News,
Infini News, RefinedWeb and FineWeb-HQ. Pinned source globs and parameters live
under `experiments.source_comparison` in [`params.yaml`](../../../params.yaml).
English follows each source's native label or declared release scope. DCLM is
deferred: its original JSONL needs whole-file reads and its Parquet copy is partial.

```bash
just dvc repro prepare_comparison   # metadata only: inventories, footers, draws
just dvc repro compare_sources      # acquire selected row groups, then estimate
just dvc metrics show
```

## Design

Each source makes four independent draws with replacement. A draw chooses a
file uniformly from the pinned frame, then one of its row groups uniformly. With
M files and G_i groups in file i, the draw probability is q = 1 / (M × G_i).
The selection is fixed before outcomes are read. Expensive draws are never
replaced, and repeated draws stay in the estimator. Acquisition reads only the
selected half-open `file_row_number` interval and projected columns, after a
range-request check. It acquires each identical group once and keeps file and
row provenance. Projected column bytes exclude HTTP overhead; network bytes are
not measured.

## Estimators

For draw d, with n_d English and y_d publisher-matched records, the
Hansen–Hurwitz estimates are:

```text
Publisher records: Y_hat = mean(y_d / q_d)
English records:   N_hat = mean(n_d / q_d)
Publisher yield:   p_hat = Y_hat / N_hat   (linearized variance)
```

Intervals are exploratory 95% Student t intervals with m − 1 degrees of
freedom, computed by statsmodels `DescrStatsW`. Totals are bounded below by
zero, and yield is bounded to [0, 1]. Zero matches, a single draw or no
variation between draws leave the uncertainty null rather than zero-width.

## Outputs and limits

`compare_sources` writes `comparison.csv`, `metrics.json`, `methods.json`,
and `summary.tex` beneath
`data/research/experiments/source-comparison/`. A paper can `\input` a table
fragment and add its own caption. Missing sources or inconsistent counts stop
the report, so a partial comparison is never published.

Four cluster draws give weak precision for rare or clustered matches. The
estimates count physical records, not unique articles. They don't establish
incremental coverage across overlapping sources, research eligibility or
company coverage over consecutive years. Choose a larger, possibly stratified
sample and the target precision before any publication-grade comparison.
