# GPU inference

Article metadata runs GLiNER2.5 Small (74M parameters) in a pinned CUDA image,
outside the locked Python workspace.

- **Setup.** `gliner-setup.sh` installs pinned packages and the pinned
  checkpoint into ignored `.runtime/`, then applies three GLiNER 2.1.0 patches.
  The patches keep attribute logits on their device, keep GLiNER's synthetic
  full stop out of source offsets, and batch span-attribute scoring.
- **Measured configuration.** FP16, DisentangledFlash attention, compiled
  extraction heads, 128-window batches, an 8,192-article buffer, four workers,
  and 384-word windows overlapping by 64 words.

```bash
just inference::setup
just dvc repro report_article_metadata      # seeded 10k benchmark and report
just inference::extract data/raw/fine-news data/processed/article-metadata
```

`gliner_extract.py` serves both the benchmark and the corpus run:

- **Order.** It processes row groups in seeded random order, so a partial run is
  a random cluster sample.
- **Resuming.** Completed row groups are written atomically and skipped by the
  same command later. It refuses to resume if the code, schema or settings have
  changed.
- **`articles/`.** One row per article, with the complete article-form and
  event-family scores for each window.
- **`mentions/`.** Companies, people, public bodies and places, with character
  offsets (`stop` is exclusive). Company mentions add local-relevance and
  financial-sentiment softmax scores.
- **`schema.json` and `progress.json`.** The label orders and model and code
  checksums, plus throughput and the remaining time.

Scores are uncalibrated. The downstream company linker resolves mentions to dated issuers.
Keep the score vectors and choose thresholds downstream.

## OpenSearch article embeddings

Run `bash infra/inference/opensearch-run.sh [output-directory]` from the root
with the OpenSearch checkpoint at revision
`d558088abac35e8932772965a85e927aedfe49c7` in `.runtime/opensearch-v1`
(config, tokenizer JSON files, backbone and `2_Dense/model.safetensors`).
The local SGLang image runs without network access. The runner uses the raw
article text, up to 8,192 tokens, with no query prompt. It mean-pools the
backbone states in FP32, applies the learned projection, L2-normalizes and
saves 2,048 FP16 components with each source id. Empty text gets a zero vector
and a false `has_text` flag. A startup probe compares against Transformers.

Each completed source row group becomes one atomic Parquet file under the
corresponding input shard path. Rerun against the same frozen input and output
to resume. Use a fresh output directory for a different corpus or model. Allow
at least 61 GiB free for outputs, including the 3 GiB filesystem reserve.
