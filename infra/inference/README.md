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

## Whole-article embeddings

From the repository root, run `bash infra/inference/gemma-run.sh`. The offline
GPU container reads the frozen Fine News shards and the Google EmbeddingGemma-300M
snapshot at revision `57c266a740f537b4dc058e1b0cda161fd15afa75` in
`.runtime/embeddinggemma-300m`. Each input receives the document prefix
`title: none | text:` followed by a space and up to 2,048 tokens including the prefix. SGLang
uses BF16 eager FlashAttention-4, FP32 mean accumulation, the model's two dense
heads, and FP32 normalization. Two requests of up to 32 articles run concurrently.

Each source row group produces one atomic Parquet file in
`data/processed/embeddinggemma-embeddings`, with source IDs in order and 768
FP16 coordinates. Blank text receives a zero vector and false `has_text`.
Rerun the command to resume against the same frozen corpus. The worker checks
two native FP32 probes on startup and reserves 3 GiB of free disk space.
Use a fresh directory for a different model or input snapshot.
