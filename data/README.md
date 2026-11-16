# Data workspace

Data follows the same layers as `dvc.yaml` and `pipeline.stages`:

- `raw/`: versioned source snapshots and provenance.
- `processed/`: reusable cleaned, deduplicated and enriched tables.
- `research/`: coverage panels, study cohorts and release datasets.
- `inputs/`: small, Git-tracked inputs to pipeline stages.

Stage commands create their output directories when implemented. Git ignores
large data payloads; track reproducible data with DVC. Keep small input files,
`.dvc` pointer files and documentation in Git.
