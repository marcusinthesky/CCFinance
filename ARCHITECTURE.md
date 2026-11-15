# Architecture

CCFinance separates code and research artifacts. Git stores source, configuration,
locks, provenance definitions and documentation. DVC will track large data and
experiment outputs once the actual stages are defined in part 2.

- `src/python/apps/pipeline` owns the CLI and data stage implementations.
- `src/python/uv.lock` locks runtime, quality, testing, packaging and DVC tools.
- `src/latex` owns the manuscript source and bibliography.
- `data` holds ignored data payloads and versioned DVC pointer files.
- `infra/nix` and `devenv.lock` own the reproducible system environment.

Tach enforces module boundaries; Ruff and strict Pyrefly check Python source.
CI executes those checks, tests and builds through the same just recipes as local
work. Setup may download dependencies; ordinary checks use cached dependencies
and do not repair authored content. LaTeX uses a versioned Tectonic asset bundle.

The Hugging Face dataset is staging, and the bucket is intended for intermediate
and experiment artifacts. Neither is accessed by scaffold commands. Pipeline
stages, provenance, study parameters, coverage criteria and remote transport are
part 2 work, rather than implied by this scaffold.

Copier answers record the source and tag for future template updates. Review
update conflicts and preserve project-specific code and configuration. The
upstream template is [Exordio](https://github.com/marcusinthesky/exordio).
