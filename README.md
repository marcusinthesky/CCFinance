# CCFinance

CCFinance is a data engineering project for filtering and enriching public
Common Crawl News (CC-News) copies for research into language in finance.

## Start

Exordio supplies the Python and LaTeX toolchains, a pinned Nix environment and CI.
Copier answers record Exordio `v0.1.1-alpha` (the documented `v0.1.0` tag was not
available in the local source).

```bash
bash infra/nix/install-devenv.sh
devenv shell
just setup
just python::run --help
just python::run stages list
just check
```

For Python alone, with Python 3.13, uv and just installed:

```bash
just python::setup
just python::check
```

## Data and reproducibility

DVC is initialized at the repository root with analytics disabled. Use:

```bash
just dvc status
just dvc dag
```

Semflow tracks the executable Python dependencies of DVC stages. When adding a
stage, run `just semflow-patch` to review its proposed fingerprints, then
`just semflow-apply` to materialize them. Commit the generated
`.semflow/hashes/` files with the DVC definition. After semantic source changes,
run `just semflow-refresh`; `just semflow-check` detects stale fingerprints.
There are no executable stages to instrument yet. The check skips fingerprint
comparison only while the stage mapping is empty; any future stage must pass
Semflow's check. Keep data, configuration and environment dependencies explicit
in DVC: Semflow's static analysis cannot discover string-driven dynamic imports.

See [Python commands](src/python/README.md), [LaTeX commands](src/latex/README.md)
and [infrastructure](infra/README.md). The scaffold's Apache-2.0 license covers
code; it does not grant rights to upstream article content.
