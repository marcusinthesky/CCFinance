# Architecture

CCFinance separates code and research artifacts. Git stores source, configuration,
locks, provenance definitions and documentation. DVC defines data dependencies
and will track large data and experiment outputs once they are materialized.

- `src/python/apps/pipeline` owns the CLI and data stage implementations.
- `src/python/uv.lock` locks runtime, quality, testing, packaging and DVC tools.
- `src/latex` owns the manuscript source and bibliography.
- `data` holds ignored data payloads and versioned DVC pointer files.
- `infra/nix` and `devenv.lock` own the reproducible system environment.

Tach enforces module boundaries; Ruff and strict Pyrefly check Python source.
pytest-layout-enforcer checks test file placement during collection and CI.
Semflow fingerprints the Python code used by DVC stages, allowing DVC to
invalidate tracked results when executable behavior changes. Stages depend
only on these fingerprints, data and parameters. They do not depend on
environment locks such as `uv.lock`, `devenv.lock` or the GLiNER requirements,
so dependency updates leave results current. Semflow cannot trace the GLiNER
stages, so they depend on their extractor modules and patches instead.
CI executes those checks, tests and builds through the same just recipes as local
work. Setup may download dependencies; ordinary checks use cached dependencies
and do not repair authored content. LaTeX uses a versioned Tectonic asset bundle.

The Hugging Face dataset is staging. DVC stores intermediate and experiment
artifacts in the private `marcusinthesky/CCFinance` bucket through its S3 gateway.
The frozen acquisition stages record their inputs without refetching them.

Each data layer groups experimental artifacts and code beneath
`experiments/<name>/`. DVC supplies artifact paths explicitly, so layers read
earlier outputs without importing earlier modules. The source comparison
prepares manifests from Hub listings and Parquet footers, then acquires only
the selected row groups through one raw publisher registry. Its shared
contracts live in `pipeline.experiments`. Research uses statsmodels for
survey estimates and LaTeX tables.

Article metadata runs GLiNER2.5 in a pinned GPU container from
`infra/inference`, outside the locked workspace. The same extractor writes the
processed benchmark and the corpus tables, and the pipeline samples and reports
the benchmark. Row groups run in seeded random order and resume from atomic
outputs. Complete uncalibrated score vectors are kept, so thresholds remain a
research decision.

Company linking scores GLiNER company mentions against dated US-listed issuers
from SEC and Wikidata snapshots. Its evaluation draws a sample without reading
linker output, so one labelled set evaluates every linker version. PydanticAI
model judges label the sample, and repeat and audit judges measure their
reliability. Reports state that labels are model-adjudicated.

The coverage audit dates and deduplicates articles, then counts each listed
issuer's raw, dated, usable and company-focused articles by year. Research
stages write pgfplots figures as CSV data and LaTeX, and Tectonic renders the
report from cached TeX resources.

Copier answers record the source and tag for future template updates. Review
update conflicts and preserve project-specific code and configuration. The
upstream template is [Exordio](https://github.com/marcusinthesky/exordio).
