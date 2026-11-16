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
dataset card describes content rights and usage restrictions.

## Restored snapshot

`data/raw/fine-news/` contains the existing publisher-filtered snapshot from
`marcusinthesky/fine-news-financial-publishers` at Hub revision
`3168f32f57107eac95a2c53f024e5e340c91ef2e`. It was copied from the local staging
repository's `data/01_intermediate/` directory, preserving 168 monthly Parquet
shards, 14,807,287 records and 20,100,064,588 Parquet bytes. Its domain CSV matches
this recipe's input. Every shard was checked against the published revision's
Git LFS SHA256 and size; Parquet metadata confirms row counts and columns.

The output's `provenance.json` records the source revision, upstream source,
domain checksum and each shard's path, SHA256, size and row count. DVC records
the complete directory in `dvc.lock` and the local cache. This restoration
preserves the published month/language layout. The reproduction command above
writes a consolidated `articles.parquet`; a fresh rebuild has not been compared
row for row with the restored snapshot.

The stage remains frozen: `dvc repro` verifies its existing output without
executing the acquisition, even with `--force`. On another checkout, restore
the output with `just dvc checkout filter_fine_news` from the local cache, or
`just dvc pull filter_fine_news` once an artifact remote contains it. No remote
cache upload was performed by this restoration.

Unfreezing or invoking the command directly runs acquisition and requires
network access and substantial resources. Use a fresh output directory when
rebuilding. DuckDB may download its `httpfs` extension on first remote access.

For a local trial, provide `--config` with a local source glob, domain CSV and
fresh output directory. The script refuses to overwrite an existing output.
Output layout, order and Parquet bytes differ from
the staging shards; selected rows have not been compared with that dataset.
