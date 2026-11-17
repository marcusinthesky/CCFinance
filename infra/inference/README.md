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

Scores are uncalibrated, and company mentions are not yet linked to issuers.
Keep the score vectors and choose thresholds downstream.
