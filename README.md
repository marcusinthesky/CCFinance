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

Shared agent instructions and Codex configuration are maintained in
[`.agents/`](.agents/README.md). `just setup` applies them; use
`just agents::preview` to preview link changes and `just agents::check` to
verify the generated links.

`just check` validates Justfile syntax and formatting alongside the other
quality gates. Run `just fmt` to format Justfiles and other source files.

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
The frozen [Fine News acquisition stage](data/inputs/fine-news/README.md) retains
the published staging snapshot and its historical selection recipe. DVC verifies
the restored output during reproduction. The
[source comparison](data/inputs/source-comparison/README.md) prepares small
probability samples using Parquet metadata before acquiring article payloads.
[Article metadata](infra/inference/README.md) is extracted on a local GPU after
a seeded benchmark; the long run resumes from completed row groups.
Keep data, configuration and environment dependencies explicit in DVC: Semflow's
static analysis cannot discover string-driven dynamic imports.

See [Python commands](src/python/README.md), [LaTeX commands](src/latex/README.md)
and [infrastructure](infra/README.md). The scaffold's Apache-2.0 license covers
code; it does not grant rights to upstream article content.
