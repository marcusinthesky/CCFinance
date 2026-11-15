# Python architecture

One uv workspace and lock own runtime, development and build dependencies.
`apps/pipeline/src/pipeline` owns the executable application:

- `cli` parses arguments and dispatches commands.
- `stages` owns data processing commands and future stage implementations.
- `__main__` exposes the same application through `python -m pipeline`.

Tach enforces the declared dependency direction from the application entry point
to CLI to stages, including type-checking imports, with cycles forbidden.
Ruff and strict Pyrefly check source and tests. Tests exercise CLI dispatch and
installed module execution; packaging is checked independently by a wheel build.

All Python recipes scrub inherited Python paths and virtual environments.
Setup is the network boundary; validation uses frozen offline dependencies.
