# Python workspace

`apps/pipeline` is an installable Typer application in a Python 3.13 uv workspace.
Run from the repository root:

```bash
just python::setup
just python::run --help
just python::run version
just python::run stages list
just python::run stages raw --help
just python::layout
just python::check
```

Data processing is organized into three layers, matching `dvc.yaml`:

| Module and CLI group | Purpose | Data location |
| --- | --- | --- |
| `pipeline.stages.raw` / `stages raw` | Preserve source snapshots and provenance | `data/raw/` |
| `pipeline.stages.processed` / `stages processed` | Build reusable cleaned and enriched tables | `data/processed/` |
| `pipeline.stages.research` / `stages research` | Curate coverage panels, cohorts and release datasets | `data/research/` |

The raw layer includes the frozen historical Fine News publisher filter described
in [its acquisition configuration](../../data/inputs/fine-news/README.md). Add other
stage commands under their owning layer,
with explicit inputs and outputs, and declare their dependencies in `dvc.yaml`.
DVC connects layers through artifacts; Python modules need not import earlier
layers to read their outputs. Importing a module performs no dataset access.

Setup installs the committed lock. Checks run offline with frozen dependencies.
Ruff checks formatting, annotations, docstrings and common correctness/security
issues; strict Pyrefly checks all app code and tests. Tach enforces module
boundaries, rejects unused dependency declarations and forbids cycles. The CLI
imports the stage router, which registers the three independent layer modules.

`pytest-layout-enforcer` checks test paths against their owning source modules
both during pytest collection and with `just python::layout`. Test paths mirror
`apps/pipeline/src/pipeline` under `apps/pipeline/tests`: for example,
`cli.py` maps to `test_cli.py`, and `stages/raw/loader.py` maps to
`stages/raw/test_loader.py`. Feature variants use `__`, as in
`test_loader__empty.py`; `include-packages` also allows tests for package
initializers. This checks existing test placement, not test coverage. Tach checks
imports and does not enforce this layout.

`just python::test` runs all tests. `test-changed` is a local optimization only.
`build` builds a wheel and source archive. `fmt` explicitly repairs formatting.
Ruff and Pyrefly run from the same uv lock locally and in CI.
