# Publisher-filter sampling methods

## Population and outcome

The experiment estimates English source records retained by the historical
115-domain allowlist, including subdomains. Each configured commit and native
Parquet glob defines a finite source frame. Fine News uses its English files;
Infini News uses its inline `eng_Latn` label; FineWeb-HQ uses `en`; RefinedWeb
declares its release English. These source-specific definitions are recorded,
not independently validated language labels.

The outcome is publisher retention. Dates, tickers, financial relevance and
article quality are not requirements in this pilot. Physical rows, rather than
distinct URLs or stories, are counted. Training weights in Fine News do not
change this record-count estimand. The original compressed DCLM source is
deferred, and its partial Parquet conversion cannot represent the full source.

## Selection

Enumerate every eligible file and its stored size at the pinned commit. Make
four independent draws with replacement: choose a file uniformly from the
frame, read its footer, then choose one of its row groups uniformly. Only
selected files require footers. Sort inventories and use a separate deterministic
seed per source. Persist every selected path, group, row bounds and probability.

For a frame of M files, with G_i groups in selected file i, the probability
of that physical group on one draw is q = 1 / (M × G_i). This is a draw
probability, not the probability of appearing at least once in the sample.
Repeated draws remain in the estimator. Identical groups are acquired once and
their counts reused, without duplicating retained sample articles.

Selection is fixed before reading outcomes. Do not replace expensive or failing
draws, select the smallest files, stop after enough matches or interpret a
convenience partition as a representative source. A costly preparation can be
deferred; changing the design requires a separately recorded experiment.

## Acquisition

Read only the selected group's half-open `file_row_number` interval and the
explicit source projection. DuckDB 1.5.6 pushes those bounds to its Parquet
reader. A local HTTP test compares transferred body bytes with a full projected
scan. Ordinary `SYSTEM` or reservoir sampling is not the I/O boundary.

The source must answer a small range request with HTTP 206 and matching source
size. There is no whole-file fallback. Group sizes and necessary column chunks
come from the footer; media and embeddings are excluded. Useful native metadata
and file/row provenance remain in the retained output. A selected group is
materialized once to reconcile input, English and retained counts.

Listed file bytes describe stored source objects. Projected compressed chunk
bytes describe selected columns before HTTP overhead, footer reads, prefetching
or retries. Retained output bytes are measured locally. Actual network bytes
are not measured and remain null. A single-group file may offer little saving.

## Estimation and uncertainty

For draw d, count English records n_d and publisher-matched English records
y_d. Let X_d = y_d / q_d and Z_d = n_d / q_d. The Hansen–Hurwitz estimates are:

```text
Publisher records: Y_hat = mean(X_d)
English records:   N_hat = mean(Z_d)
Publisher yield:   p_hat = Y_hat / N_hat
Var(Y_hat):       sum((X_d - Y_hat)^2) / (m × (m - 1))
Var(p_hat):       sum((X_d - p_hat × Z_d)^2) / (m × (m - 1) × N_hat^2)
```

Totals and their design-variance estimates are unbiased for independent
replacement draws. Yield is a ratio estimate with approximate linearized
variance, not an exactly unbiased estimator. Unequal group counts make an
unweighted pooled sample yield inappropriate for population inference.

Approximate 95% intervals use the Student t critical value with m - 1 degrees
of freedom, with totals bounded below by zero and yield bounded to [0, 1].
Four draws provide only three degrees of freedom. Rare or skewed group totals
can make these intervals unreliable; label them exploratory. Zero matches,
insufficient draws or degenerate variation leave the relevant uncertainty null,
with an insufficient-evidence status. Zero English rows also leave yield null.

Statsmodels `DescrStatsW` receives the probability-expanded draw values with
unit frequency weights. Its mean, standard error and t interval provide the
same total estimator; the yield uses the linearized residuals above. These are
estimates over independent group draws, rather than over individual source rows.
`Summary` and `SimpleTable` render the estimates in LaTeX. The full summary
retains methods notes, while individual tables can be included with paper captions.

The implementation tests weights against exact expectations over small finite
frames, validates repeated draws and count reconciliation, and keeps physical
sample counts separate from statistical draw totals. Sampling uncertainty does
not include source omissions, language errors or publisher-registry validity.

## Further inference

This pilot cannot establish unique research articles, cross-source incremental
yield or companies meeting article thresholds over consecutive publication
years. Source time composition differs, and crawl time is not publication time.
Treat capture partitions as source provenance rather than an annual coverage
estimate. Plan a larger, potentially stratified probability sample and a desired
precision before a publication-grade comparison. Do not use outcome-dependent
stopping without a suitable sequential design.

## References

- [DuckDB Parquet metadata](https://duckdb.org/docs/1.5/data/parquet/metadata)
  describes group counts and compressed column sizes.
- [DuckDB sampling](https://duckdb.org/docs/1.5/sql/query_syntax/samples)
  describes execution-vector sampling and reservoir behavior.
- [Hugging Face Parquet conversion](https://huggingface.co/docs/dataset-viewer/parquet)
  describes partial conversions and their scope.
- [Knottnerus and van Duin, Appendix A](https://www.scb.se/contentassets/ca21efb41fee47d293bbee5bf7be7fb3/variances-in-repeated-weighting-with-an-application-to-the-dutch-labour-force-survey.pdf#page=17)
  gives the Hansen–Hurwitz total and variance formulas.
- [Statsmodels LaTeX summaries](https://www.statsmodels.org/stable/generated/statsmodels.iolib.summary.Summary.as_latex.html)
  describes summary export and recommends individual table export when columns differ.
