# /// script
# requires-python = ">=3.13,<3.14"
# dependencies = ["duckdb==1.5.6", "pyarrow==26.0.0"]
# ///
"""Export the frozen CCFinance metadata as one nested row per upstream capture."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
RAW = DATA / "raw/fine-news"
SHARD_BYTES = 256 * 1024**2

# Projection and nested struct casts deliberately exclude source text and aliases.
GROUP_QUERY = """
WITH spans AS (
    SELECT id, list(struct_pack(entity_type, start, stop, confidence,
                    local_relevance, financial_sentiment)
                    ORDER BY start, stop, entity_type) AS mentions
    FROM read_parquet($spans) GROUP BY id
), links AS (
    SELECT id, list(struct_pack(start, stop, cik, link_score, method, self_publisher,
                candidates := candidates::STRUCT(cik BIGINT, score DOUBLE)[])
                ORDER BY start, stop, cik) AS mention_links
    FROM read_parquet($links) GROUP BY id
), issuers AS (
    SELECT id, list(struct_pack(cik, day, n_mentions, link_score, relevance_substantive,
                sentiment, first_offset_share, self_publisher, ticker, exchange,
                evidence := evidence::STRUCT(start INTEGER, stop INTEGER,
                                              method VARCHAR, score DOUBLE)[])
                ORDER BY cik) AS issuer_links
    FROM read_parquet($issuers) GROUP BY id
)
SELECT q.*, w.text_sha256,
    w.windows::STRUCT(start INTEGER, stop INTEGER, article_form FLOAT[],
                      event_family FLOAT[])[] AS windows,
    coalesce(s.mentions, []) AS mentions,
    coalesce(m.mention_links, []) AS mention_links,
    coalesce(i.issuer_links, []) AS issuer_links
FROM read_parquet($vectors, file_row_number=true) v
JOIN quality q USING (id)
JOIN read_parquet($windows) w USING (id)
LEFT JOIN spans s USING (id)
LEFT JOIN links m USING (id)
LEFT JOIN issuers i USING (id)
ORDER BY v.file_row_number
"""
LEDGER_QUERY = """
COPY (
    SELECT a.id, a.host, a.published, a.captured, a.lag_days, a.date_status,
        a.text_length, a.copies, a.duplicate_of, a.duplicate_kind,
        a.article_form, a.extraction_status, a.canonical, a.usable,
        r.metadata.warc_filename AS warc_filename, r.metadata.capture_month AS month,
        nullif(regexp_extract(r.metadata.url, '^(https?://[A-Za-z0-9.-]+(?::[0-9]+)?'
            || '(?:/[^?#[:space:]]*)?)(?:[?#]|$)', 1), '') AS page_url
    FROM read_parquet($quality) a JOIN read_parquet($source) r USING (id)
) TO $output (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY(month))
"""


def sha256(path: Path) -> str:
    """Hash the actual bytes distributed by the Hub."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def export_shard(
    con: duckdb.DuckDBPyConnection, source: Path, output: Path
) -> tuple[list[Path], int]:
    """Align each row group with its original FP16 vectors before writing it."""
    stem = "--".join(source.with_suffix("").parts)
    vector_dir = PROCESSED / "embeddinggemma-embeddings" / source
    groups = sorted(vector_dir.glob("group-*.parquet"))
    if len(groups) != pq.ParquetFile(RAW / source).num_row_groups:
        raise ValueError(f"Missing embedding group for {source}")
    files = []
    rows = 0
    writer = None
    try:
        for index, path in enumerate(groups):
            name = f"{stem}--{index:03}.parquet"
            table = con.execute(
                GROUP_QUERY,
                {
                    "spans": str(PROCESSED / "article-metadata/mentions" / name),
                    "links": str(PROCESSED / "company-links/mentions" / name),
                    "issuers": str(PROCESSED / "company-links/articles" / name),
                    "windows": str(PROCESSED / "article-metadata/articles" / name),
                    "vectors": str(path),
                },
            ).to_arrow_table()
            vectors = pq.read_table(path, columns=["id", "embedding", "has_text"])
            ids = vectors["id"].cast(pa.string())
            if not table["id"].cast(pa.string()).equals(ids):
                raise ValueError(f"Article IDs do not align in {name}")
            if vectors["embedding"].type != pa.list_(pa.float16(), 768):
                raise ValueError(f"Unexpected vector type in {name}")
            for field in ("embedding", "has_text"):
                table = table.append_column(field, vectors[field])
            for field, directory in (
                ("mentions", "article-metadata/mentions"),
                ("mention_links", "company-links/mentions"),
                ("issuer_links", "company-links/articles"),
            ):
                expected = pq.read_metadata(PROCESSED / directory / name).num_rows
                observed = pc.sum(pc.list_value_length(table[field])).as_py() or 0
                if observed != expected:
                    raise ValueError(f"{field} count mismatch in {name}")
            if writer is None:
                dest = (
                    output / f"{source.parts[0]}-{source.stem}-{len(files):03}.parquet"
                )
                files.append(dest)
                writer = pq.ParquetWriter(
                    dest,
                    table.schema,
                    compression="zstd",
                    compression_level=3,
                    use_dictionary=[
                        "host",
                        "date_status",
                        "duplicate_kind",
                        "article_form",
                        "extraction_status",
                        "warc_filename",
                    ],
                    use_byte_stream_split=["embedding.list.element"],
                    write_statistics=["published", "captured", "host", "usable"],
                )
            writer.write_table(table, row_group_size=4096)
            rows += table.num_rows
            if files[-1].stat().st_size >= SHARD_BYTES:
                writer.close()
                writer = None
    finally:
        if writer is not None:
            writer.close()
    return files, rows


def build(output: Path) -> None:
    """Assemble one dataset in a fresh directory, reconciling every input shard."""
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    provenance = json.loads((RAW / "provenance.json").read_text())
    manifest = []
    with TemporaryDirectory(dir=output.parent, prefix=".ccfinance-") as scratch:
        staging = Path(scratch) / "release"
        shards = staging / "data"
        docs = staging / "documentation"
        shards.mkdir(parents=True)
        docs.mkdir()
        with duckdb.connect() as con:
            con.execute("SET threads=4")
            con.execute("SET memory_limit='5GB'")
            con.execute("SET TimeZone='UTC'")
            con.execute("SET temp_directory=?", [scratch])
            con.execute(
                LEDGER_QUERY,
                {
                    "quality": str(PROCESSED / "articles/articles.parquet"),
                    "source": [str(RAW / s["path"]) for s in provenance["shards"]],
                    "output": str(Path(scratch) / "months"),
                },
            )
            current_month = None
            for shard in provenance["shards"]:
                source = Path(shard["path"])
                month = source.parts[0]
                if month != current_month:
                    con.execute(
                        "CREATE OR REPLACE TEMP TABLE quality AS SELECT "
                        "* EXCLUDE(month) FROM read_parquet(?)",
                        [str(Path(scratch) / "months" / f"month={month}/*.parquet")],
                    )
                    current_month = month
                paths, rows = export_shard(con, source, shards)
                if rows != shard["records"]:
                    raise ValueError(f"Exported {rows} rows for {source}")
                for path in paths:
                    manifest.append(
                        {
                            "path": path.relative_to(staging).as_posix(),
                            "rows": pq.read_metadata(path).num_rows,
                            "bytes": path.stat().st_size,
                            "sha256": sha256(path),
                        }
                    )
                print(source, rows, flush=True)
        schema = json.loads((PROCESSED / "article-metadata/schema.json").read_text())
        (docs / "gliner-schema.json").write_text(
            json.dumps(
                {
                    k: schema[k]
                    for k in ("schema", "labels", "model_sha256", "code_sha256")
                },
                indent=2,
            )
            + "\n"
        )
        shutil.copyfile(
            DATA / "inputs/fine-news/domains.csv", docs / "publisher-hosts.csv"
        )
        shutil.copyfile(
            PROCESSED / "body-vector-audit/summary.json", docs / "vector-audit.json"
        )
        (docs / "manifest.json").write_text(
            json.dumps(
                {
                    "upstream": provenance["upstream_source"],
                    "staging_revision": provenance["revision"],
                    "records": provenance["records"],
                    "files": manifest,
                },
                indent=2,
            )
            + "\n"
        )
        shutil.copyfile(Path(__file__).with_name("card.md.in"), staging / "README.md")
        staging.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output.resolve())
