# Data workspace

Data follows the same layers as `dvc.yaml` and `pipeline.stages`:

- `raw/`: versioned source snapshots and provenance.
- `processed/`: reusable cleaned, deduplicated and enriched tables.
- `research/`: coverage panels, study cohorts and release datasets.
- `inputs/`: small, Git-tracked inputs to pipeline stages.

Experiments use the same name within each layer. Source-comparison manifests
and samples live in `raw/experiments/source-comparison/`; estimates and paper
tables live in `research/experiments/source-comparison/`. The article-metadata
benchmark lives in `processed/experiments/article-metadata/` and its report in
`research/experiments/article-metadata/`; the corpus run writes
`processed/article-metadata/`. DVC connects these artifacts;
an experimental result does not become a release dataset merely by moving it.

Stage commands create their output directories when implemented. Git ignores
large data payloads; track reproducible data with DVC. Keep small input files,
`.dvc` pointer files and documentation in Git.
