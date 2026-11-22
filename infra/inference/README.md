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

The DVC stage `embed_article_bodies` owns the completed corpus. After an
out-of-band GPU run, `just dvc commit embed_article_bodies` records the
artifact in place. Run `just dvc repro verify_body_vectors` to reconcile
source IDs, row order, text flags, dimensions and norms across every group.
The Lopez-Lira–Tang study reads the verified vectors by article ID.

### Throughput and fidelity

Run `BENCHMARK=1 bash infra/inference/gemma-run.sh .runtime/gemma-benchmark`
for two passes through 2,304 articles on six frozen shards. Each pass times the
production writer from reading through Parquet close. The benchmark checks IDs
in source order and compares 48 length-stratified vectors to native FP32,
including the learned dense projections. The acceptance floor is 0.999 minimum
cosine and 127.11 articles/s on the second pass on the RTX 5060 Ti.

The [repeat measurements](embedding-throughput.csv) use the image digest in the
launcher. Reference cosines apply to the final saved output per configuration.
BF16 FA4 sustained 133.8 articles/s. FlashInfer and TensorRT-LLM MHA reached
140.0 and 140.3 but their minimum cosines fell below 0.62. The pinned prefill
paths apply causal masking to Gemma's bidirectional layer marker. Breakable
graphs replayed 139 times on the warm pass and reached 117.9 articles/s.
FA4 dynamic FP8 also missed the fidelity floor (0.99636).

The retained writer reached 134.4 articles/s on the warm pass. It initializes
the engine before setting the native reference model's CPU thread count and
warms a production-sized request before checking the short probes.
