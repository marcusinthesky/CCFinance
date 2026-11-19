---
type: changelog
description: Changes to CCFinance data engineering, research workflows and repository tooling.
---

# CHANGELOG

## Unreleased

### Added

- Article quality table (date status, residual duplicates, article form and
  syndication copies) and an SEC public-float snapshot for issuer size.
- Company linking to US-listed SEC issuers: SEC and Wikidata issuer snapshot, dated
  tickers and aliases, a scored linker and a model-adjudicated evaluation.
- GLiNER2.5 article-metadata extraction with typed mentions, company relevance
  and sentiment scores, article form and event families, plus a seeded benchmark.
- Source-comparison DVC stages with metadata preparation, selective Parquet reads,
  exploratory publisher-filter yield estimates and statsmodels LaTeX tables.
- Frozen Fine News acquisition recipe with the historical publisher filter.
- Python and LaTeX toolchains generated from Exordio, with locked dependencies.
- Typer `pipeline` application and a namespace for data processing stages.
- DVC repository configuration and a workspace for research data.
- Ruff, strict Pyrefly, Tach, pytest-layout-enforcer, tests and package builds
  in local checks and CI.
- Planning and local reference workflows with Schematter validation and Insitu views.
- A validated changelog with a closed set of change categories.
- Semflow integration for reviewing and checking semantic DVC fingerprints.
- Justfile formatting and analysis checks in pre-commit and CI.
- Agent skill schema and validation for metadata, structure and length.
- AgentSync-managed shared instructions, skills and Codex configuration.

### Changed

- DVC stages no longer depend on environment locks, only on Semflow fingerprints
  or extractor code, data and parameters, so dependency updates keep results current.
- Restored the published Fine News shards with verified checksums and provenance
  so the frozen acquisition stage has real outputs for DVC to validate.
- Grouped experiments within each data layer and consolidated source mappings
  and validated artifact contracts across sampling and research reports.
- Organized the pipeline into `raw`, `processed` and `research` layers, with
  matching Python modules, CLI groups and proposed data paths.
