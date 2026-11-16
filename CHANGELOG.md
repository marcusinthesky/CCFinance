---
type: changelog
description: Changes to CCFinance data engineering, research workflows and repository tooling.
---

# CHANGELOG

## Unreleased

### Added

- Python and LaTeX toolchains generated from Exordio, with locked dependencies.
- Typer `pipeline` application and a namespace for data processing stages.
- DVC repository configuration and a workspace for research data.
- Ruff, strict Pyrefly, Tach, tests and package builds in local checks and CI.
- Planning and local reference workflows with Schematter validation and Insitu views.
- A validated changelog with a closed set of change categories.
- Semflow integration for reviewing and checking semantic DVC fingerprints.
- pytest-layout-enforcer for source-aligned test paths.
- Justfile formatting and analysis checks in pre-commit and CI.
- Agent skill schema and validation for metadata, structure and length.
- AgentSync-managed shared instructions, skills and Codex configuration.

### Changed

- Organized the pipeline into `raw`, `processed` and `research` layers, with
  matching Python modules, CLI groups and proposed data paths.
