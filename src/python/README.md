# Python workspace

`apps/pipeline` is an installable Typer application in a Python 3.13 uv workspace.
Run from the repository root:

```bash
just python::setup
just python::run --help
just python::run version
just python::run stages list
just python::check
```

Setup installs the committed lock. Checks run offline with frozen dependencies.
Ruff checks formatting, annotations, docstrings and common correctness/security
issues; strict Pyrefly checks all app code and tests. Tach enforces explicit
module boundaries, rejects unused dependency declarations and forbids cycles. The CLI may depend on
stages; stages must not import the CLI. New stage files inherit the stages boundary; declare finer module boundaries
and their allowed dependencies in `tach.toml` as stages grow.

Keep CLI argument parsing in `pipeline.cli`; implement research stages under
`pipeline.stages`, with explicit inputs and outputs. Add corresponding DVC
stages at the repository root in part 2. No dataset access occurs on import.

`just python::test` runs all tests. `test-changed` is a local optimization only.
`build` builds a wheel and source archive. `fmt` explicitly repairs formatting.
Ruff and Pyrefly run from the same uv lock locally and in CI.
