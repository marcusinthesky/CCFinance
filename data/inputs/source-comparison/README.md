# Source comparison

This pilot measures English source records retained by the same publisher
allowlist as the historical Fine News acquisition. It compares Fine News,
Infini News, RefinedWeb and FineWeb-HQ. DCLM is deferred: its original compressed
JSONL requires whole-file reads, while its converted Parquet is partial.

The shared parameters and pinned native source globs live under
`experiments.source_comparison` in [`params.yaml`](../../../params.yaml).
Dataset keys identify small Python source
projections; the configuration contains no executable SQL. English follows each
source's native labels or declared release scope. No language model is run.

## Prepare

Inside `devenv shell`, after `just python::setup`:

```bash
just dvc repro prepare_comparison
```

This runs the metadata-only `foreach` stages. Each source produces an inventory,
selected-file Parquet metadata and `manifest.json` beneath
`data/raw/experiments/source-comparison/manifests/`. The inventory records eligible paths,
object identities and stored sizes at the configured commit. The manifest
records four replacement draws, source row bounds, probabilities and compressed
sizes for the columns needed by the extractor.

Preparation checks that the server answers an eight-byte range request with a
matching partial response. It then reads selected Parquet footers. It does not
acquire article text, media or embeddings. A source with large row groups can
still require substantial transfer later: inspect its projected bytes first.
Projected column bytes exclude footer reads, HTTP overhead, prefetching and
retries; they are not a measured network total.

The preparation on 2026-11-16 produced the following selection at the commits
in `params.yaml`, recorded by the preparation entries in `dvc.lock`:

| Source | Selected rows | Projected columns (MiB) | Selected-file footers (MiB) |
| --- | ---: | ---: | ---: |
| Fine News | 16,384 | 29.44 | 13.86 |
| Infini News | 100,141 | 107.11 | 0.04 |
| RefinedWeb | 4,000 | 6.21 | 1.91 |
| FineWeb-HQ | 4,000 | 5.61 | 4.34 |

Each source has four unique selected groups. These are metadata-based sizes,
not acquired article counts or observed yield. Prepared artifacts are in the
local DVC cache; no remote artifact upload has been performed.

## Acquire and compare

After reviewing the prepared selection and transfer estimates:

```bash
just dvc repro sample_comparison
just dvc repro compare_sources
just dvc metrics show
```

Sampling acquires article payloads. Reproducing `compare_sources` also runs any
missing or stale upstream sampling stages. The historical `filter_fine_news`
stage remains frozen and independent of this experiment.

Each acquisition writes filtered group Parquet files and `counts.json` beneath
`data/raw/experiments/source-comparison/samples/`. Records retain text, native identifiers
where available, useful native metadata, and source file/row provenance.
Repeated selections acquire one physical copy but retain every draw in the
counts used for estimation. Samples preserve records rather than deduplicating
articles. No ticker, date, relevance or body-length qualification is applied.

The research stage writes `comparison.csv`, `metrics.json` and `methods.json`,
plus LaTeX summary and table fragments,
beneath `data/research/experiments/source-comparison/`. Reports distinguish observed counts
from weighted population estimates, and stored source bytes from projected
selected-column bytes and retained output bytes. Network bytes remain unknown.
Missing sources or inconsistent counts prevent publication of the comparison.
Only configured datasets are required; an intentional subset is supported.

## Include estimates in a paper

Statsmodels formats the survey estimates and their confidence intervals into
`summary.tex`, `yield.tex` and `population.tex`. The full summary includes methods
notes. Individual tables use `SimpleTable.as_latex_tabular()` so each fragment
keeps its own columns. Yield and its confidence bounds are percentages; JSON
and CSV retain the underlying proportions. Missing bounds are printed as `--`.

After acquisition and reporting, use the fragment from a manuscript in
`src/latex/`:

```latex
% Preamble
\usepackage{booktabs}

% Body: complete summary with methods notes
\input{../../data/research/experiments/source-comparison/summary.tex}

% Or include an individual table with an authored caption
\begin{table}[htbp]
  \centering
  \input{../../data/research/experiments/source-comparison/yield.tex}
  \caption{Exploratory publisher-filter yield and 95\% confidence bounds.}
\end{table}
```

`population.tex` reports estimated publisher-matched record counts and their
bounds. These files are DVC outputs generated from the same metrics as the CSV
and JSON. Preparation alone does not create estimates or LaTeX reports.

## Interpret

Four independently selected groups provide a small acquisition pilot, with weak
precision for rare or clustered publisher matches. Population totals use the
recorded draw probabilities; uncertainty is exploratory. Zero matches or
degenerate variation do not establish a precise zero population yield.

The estimates concern publisher-matched records in the declared snapshots.
They do not establish unique articles, incremental coverage across overlapping
sources, research eligibility or consecutive-year company coverage. Fine News's
training sampling weights are not this experiment's sampling probabilities.
Infini News's file-size inventory includes non-English records.

See the [sampling methods](../../../.context/plan/dataset-research/tasks/source-comparison/methods.md)
for the design, estimators and limitations. Later pilots should choose their
sample size and any temporal strata before observing acquisition outcomes.
