# Python architecture

One uv workspace and lock own runtime, development and build dependencies.
`apps/pipeline/src/pipeline` owns the executable application:

- `cli` parses arguments and dispatches commands.
- `stages` registers the data layer command groups.
- `stages.raw` owns source acquisition and provenance.
- `stages.processed` owns cleaning, deduplication and enrichment.
- `stages.research` owns coverage panels, study cohorts and release datasets.
- `__main__` exposes the same application through `python -m pipeline`.

Tach enforces the declared dependency direction from the application entry point
to CLI to the stage router and its independent layer modules, including
type-checking imports, with cycles forbidden. Artifact dependencies in DVC
connect the layers; no cross-layer Python imports are currently needed.
pytest-layout-enforcer checks that each test file maps to a source module;
Tach's import boundaries address a separate concern. Ruff and strict Pyrefly
check source and tests. Tests exercise CLI dispatch and
installed module execution; packaging is checked independently by a wheel build.

All Python recipes scrub inherited Python paths and virtual environments.
Setup is the network boundary; validation uses frozen offline dependencies.
