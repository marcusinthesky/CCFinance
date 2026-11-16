# Data workspace

Data follows the same layers as `dvc.yaml` and `pipeline.stages`:

- `raw/`: versioned source snapshots and provenance.
- `processed/`: reusable cleaned, deduplicated and enriched tables.
- `research/`: coverage panels, study cohorts and release datasets.

Stage commands create their output directories when implemented. Git ignores
data payloads; track reproducible inputs and outputs with DVC. Keep `.dvc`
pointer files and documentation in Git.
