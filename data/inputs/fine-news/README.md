# Fine News acquisition

`filter_fine_news` documents the historical staging selection from
[Fine News](https://huggingface.co/datasets/ksolovev/fine-news) at the revision
in [acquisition.json](acquisition.json). It selects `eng_Latn` capture-month
shards and the exact 115-hostname [allowlist](domains.csv), including subdomains.
The hostname comes from `metadata.url_hostname`, falling back to `metadata.url`
when blank. One query reads the input glob and writes `text`, `id` and `metadata`
to `data/raw/fine-news/articles.parquet`.

This is the historical source filter, not a reviewed publisher list or a
research-ready article corpus. Fine News applies its own filters and
deduplication; capture month is not necessarily publication month. The upstream
dataset card describes content rights and usage restrictions. No full output has
been built, verified or cached here, and no DVC lock entry is claimed.

The stage is frozen: `dvc repro` will not execute it, even with `--force`.
Since the declared output is absent, targeting it currently reports missing data.
After obtaining or rebuilding and verifying the output, track its actual state
before relying on it downstream. Unfreezing or invoking the command directly can
run the acquisition and requires network access and substantial resources.
DuckDB may download its `httpfs` extension on first remote access.

For a local trial, provide `--config` with a local source glob, domain CSV and
fresh output directory. The script refuses to overwrite an existing output.
Output layout, order and Parquet bytes differ from
the staging shards; selected rows have not been compared with that dataset.
