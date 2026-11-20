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
`processed/article-metadata/`. Issuer references live in `raw/issuers/` and
`processed/issuers/` (see `inputs/issuers/README.md`); company links in
`processed/company-links/`, evaluated under `experiments/company-links/`.
`processed/articles/` dates and deduplicates every article, and SEC public
float for issuer size lives in `raw/public-float/` and
`processed/public-float/`. The firm-year coverage panel lives in
`research/coverage/` and its audit in `research/experiments/coverage/` (see
`inputs/coverage/README.md`). DVC connects these artifacts; an experimental
result does not become a release dataset merely by moving it.

The [company-embedding validation protocol](inputs/entity-embeddings/README.md)
defines a blinded buyer-versus-target retrieval test and its fixed sample.

Stage commands create their output directories when implemented. Git ignores
large data payloads; track reproducible data with DVC. Keep small input files,
`.dvc` pointer files and documentation in Git.

## Backup and restore

The default DVC remote uses the private Hugging Face bucket
`marcusinthesky/CCFinance`, under `dvc-store/`. In the pinned devenv shell,
supply your Hugging Face S3 access key and secret through local DVC settings
(`access_key_id` and `secret_access_key` on `hf-bucket`) or AWS credentials.
Raw Fine News shards are already published on HF Datasets. The acquisition
output sets `push: false` so DVC uploads skip that snapshot.
Use `just dvc push` to back up eligible cached outputs, `just dvc status --cloud` to
compare them with the bucket, and `just dvc pull` to restore them.
