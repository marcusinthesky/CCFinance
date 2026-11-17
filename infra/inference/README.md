# GPU inference

Article metadata runs GLiNER2.5 Small (74M parameters) in a pinned CUDA image,
outside the locked Python workspace. `gliner-setup.sh` installs the pinned
packages, applies three small GLiNER 2.1.0 patches and downloads the pinned
checkpoint into ignored `.runtime/`. The patches don't change the model weights:

- `cuda-attributes` indexes attribute logits on the device that holds them.
- `window-offsets` keeps the full stop GLiNER appends to a window out of
  source offsets.
- `batched-attributes` scores every decoded span's attributes in one GPU call.

```bash
just inference::setup
just dvc repro report_article_metadata      # seeded 10k benchmark and report
just inference::extract data/raw/fine-news data/processed/article-metadata
```

The measured configuration is FP16 with DisentangledFlash attention and
compiled extraction heads. It runs 128-window GPU batches over an 8,192-article
buffer with four preprocessing workers, and 384-word windows overlapping by 64
words. Batching was the largest speed-up. FP8 and NVFP4 were slower and changed
predictions more.

`gliner_extract.py` serves both the benchmark and the corpus run. It processes
Parquet row groups in a seeded random order, so a partial run is a random
cluster sample. Each completed row group is written atomically and skipped on
the next run, so re-running the same command resumes the work. If the code,
schema or settings changed, the extractor refuses to resume an existing output.
`progress.json` reports throughput and the remaining time.

The output has three parts:

- `articles/*.parquet`: one row per article, with a status and the article
  form. Each window keeps its complete article-form softmax and event-family
  sigmoid scores.
- `mentions/*.parquet`: one row per company, person, public body or place
  mention, with character offsets (`stop` is exclusive). Company mentions add
  local-relevance and financial-sentiment softmax scores.
- `schema.json`: the label orders, the GLiNER schema, and checksums for the
  model and code.

Scores are uncalibrated. A 100-article pilot found diffuse company sentiment and
some confident entity-type errors. Company mentions are not yet linked to
issuers, and local relevance does not show that a company is an article's main
subject. Retain the score vectors and choose thresholds downstream.
