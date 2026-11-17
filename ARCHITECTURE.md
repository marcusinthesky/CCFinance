# Architecture

CCFinance separates code and research artifacts. Git stores source, configuration,
locks, provenance definitions and documentation. DVC defines data dependencies
and tracks materialized source snapshots and experiment outputs.

- `src/python/apps/pipeline` owns the CLI and data stage implementations.
- `src/python/uv.lock` locks runtime, quality, testing, packaging and DVC tools.
- `src/latex` owns the manuscript source and bibliography.
- `data` holds ignored data payloads and versioned DVC pointer files.
- `infra/nix` and `devenv.lock` own the reproducible system environment.

Tach enforces module boundaries; Ruff and strict Pyrefly check Python source.
pytest-layout-enforcer checks test file placement during collection and CI.
Semflow fingerprints the Python code used by DVC stages, allowing DVC to
invalidate tracked results when executable behavior changes.
CI executes those checks, tests and builds through the same just recipes as local
work. Setup may download dependencies; ordinary checks use cached dependencies
and do not repair authored content. LaTeX uses a versioned Tectonic asset bundle.

The Hugging Face dataset is staging, and the bucket is intended for intermediate
and experiment artifacts. The frozen raw acquisition stage documents the
historical selection without fetching its output. Company labels and coverage
are provisional experiments; release validation and remote artifact transport
remain future work. The raw comparison stages prepare
sampling manifests from Hub listings and Parquet footers, then acquire only the
selected row groups through the shared publisher filter. Research aggregation
reads those artifacts without importing raw-stage modules. DVC connects these
steps; pinned source revisions and recorded draw probabilities define the
experiment's population and sampling design.

The article-labeling experiment adopts checksum-verified CPU company candidates
and materializes compact source-linked selections without copying article bodies.
Native Kev runs in a separately pinned GPU environment; the pipeline communicates
through typed System One requests. Article-company probabilities and filtering
policies remain separate, with resumable checkpoints and explicit unresolved
outcomes. The research layer reconciles candidate and model-scored coverage and
reports runtime estimates without treating AI agreement as human validation.
Completed pilots remain frozen. Full scoring uses compressed source-record
chunks, a resumable request ledger and explicit pending counts. Separate runtime
profiles preserve GPU memory experiments without overwriting completed evidence.

Each data layer groups experimental artifacts beneath `experiments/<name>/`.
Experimental stage code follows the same grouping under its owning layer.
`pipeline.experiments.source_comparison` defines shared parameters and artifacts;
Tach permits raw and research to depend on these contracts without importing one
another. Raw publisher extraction owns one source-field registry, deriving both
SQL projections and projected column sizes from it. DVC supplies artifact paths
explicitly. Research uses statsmodels for survey-estimate summaries and LaTeX
tables; it preserves the probability-sampling design.

Copier answers record the source and tag for future template updates. Review
update conflicts and preserve project-specific code and configuration. The
upstream template is [Exordio](https://github.com/marcusinthesky/exordio).
