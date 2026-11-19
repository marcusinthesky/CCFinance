# Fine News acquisition

`filter_fine_news` documents the historical staging selection from
[Fine News](https://huggingface.co/datasets/ksolovev/fine-news) at the revision
in [acquisition.json](acquisition.json). It selects `eng_Latn` capture-month
shards and the exact 115-hostname [allowlist](domains.csv), including subdomains.
The hostname comes from `metadata.url_hostname`, or from `metadata.url` when
that is blank. One query writes `text`, `id` and `metadata` to
`data/raw/fine-news/articles.parquet`. This is the historical source filter, not
a reviewed publisher list or a research-ready corpus. Capture month is not
necessarily publication month. The upstream dataset card describes content
rights and usage restrictions.

## Restored snapshot

`data/raw/fine-news/` holds the published snapshot of
`marcusinthesky/fine-news-financial-publishers` at Hub revision
`3168f32f57107eac95a2c53f024e5e340c91ef2e`: 168 monthly Parquet shards,
14,807,287 records and 20,100,064,588 bytes. Each shard matches the revision's
Git LFS SHA256 and size, and `provenance.json` records them. The stage is
frozen, so `dvc repro` verifies this output rather than re-running acquisition.
On another checkout, run `just dvc pull filter_fine_news` with the private
bucket credentials to restore the recorded snapshot.

Unfreezing the stage, or passing `--config` with a local glob and a fresh output
directory, runs the acquisition itself and refuses to overwrite existing output.
That writes one consolidated file, whose layout and bytes differ from the
restored shards. Its selected rows have not been compared with the snapshot row
for row.
