"""Verify the published article order and stored EmbeddingGemma vectors."""

import json
from pathlib import Path
from typing import Annotated

import duckdb
import typer

MODEL = {
    "model": "google/embeddinggemma-300m",
    "revision": "57c266a740f537b4dc058e1b0cda161fd15afa75",
    "prefix": "title: none | text: ",
    "max_tokens": "2048",
}


def verify_body_vectors(
    source: Annotated[Path, typer.Option(help="Frozen Fine News directory.")],
    vectors: Annotated[Path, typer.Option(help="Completed per-group embedding files.")],
    output: Annotated[Path, typer.Option(help="Verified corpus summary JSON.")],
) -> None:
    """Check every ID, text flag, vector and row-group boundary before joining."""
    manifest = json.loads((source / "provenance.json").read_text())
    sources = [source / entry["path"] for entry in manifest["shards"]]
    if len(sources) != len(set(sources)) or set(sources) != set(
        source.rglob("*.parquet")
    ):
        raise ValueError("Source inventory differs from the frozen manifest")
    files = {path for path in vectors.rglob("*.parquet") if path.is_file()}
    groups = present = 0
    with duckdb.connect() as con:
        con.execute("SET threads=1")
        con.execute("SET memory_limit='1GB'")
        total, unique = con.execute(
            "SELECT count(*), count(DISTINCT id) FROM read_parquet(?)",
            [str(source / "**/*.parquet")],
        ).fetchone() or (0, 0)
        if not total or total != unique or total != manifest["records"]:
            raise ValueError("Incomplete, null or duplicate source IDs")
        for entry in manifest["shards"]:
            shard = source / entry["path"]
            con.execute(
                r"""CREATE OR REPLACE TEMP TABLE expected AS
                   SELECT file_row_number AS pos, id,
                     coalesce(regexp_matches(text, '[^\s\p{Z}\x1C-\x1F\x{85}]'),
                              false) AS has_text
                   FROM read_parquet(?, file_row_number=true)""",
                [str(shard)],
            )
            sizes = con.execute(
                """SELECT row_group_id, row_group_num_rows FROM parquet_metadata(?)
                   WHERE column_id=0 ORDER BY row_group_id""",
                [str(shard)],
            ).fetchall()
            start = 0
            for group, size in sizes:
                part = vectors / entry["path"] / f"group-{group:04d}.parquet"
                if part not in files:
                    raise ValueError(f"Missing vector group {part}")
                files.remove(part)
                metadata = dict(
                    con.execute(
                        "SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)",
                        [str(part)],
                    ).fetchall()
                )
                if any(metadata.get(k) != v for k, v in MODEL.items()):
                    raise ValueError(f"Unexpected model metadata in {part}")
                numeric = con.execute(
                    """WITH actual AS (
                         SELECT file_row_number + $start AS pos, id, has_text,
                           len(embedding) AS dims,
                           list_inner_product(embedding,embedding) AS norm_sq
                         FROM read_parquet($part, file_row_number=true)
                       ), wanted AS (
                         SELECT * FROM expected WHERE pos >= $start AND pos < $stop
                       )
                       SELECT countif(a.has_text), countif(
                         a.id IS NULL OR w.id IS NULL OR a.id <> w.id
                         OR a.has_text IS DISTINCT FROM w.has_text
                         OR a.dims IS DISTINCT FROM 768 OR a.norm_sq IS NULL
                         OR NOT isfinite(a.norm_sq)
                         OR abs(a.norm_sq - 1) > 0.002 AND w.has_text
                         OR a.norm_sq <> 0 AND NOT w.has_text)
                       FROM wanted w FULL JOIN actual a USING (pos)""",
                    {"part": str(part), "start": start, "stop": start + size},
                ).fetchone()
                if numeric is None or numeric[1]:
                    raise ValueError(f"Vector alignment, size, flag or norm in {part}")
                present += numeric[0]
                start += size
                groups += 1
            if start != entry["records"]:
                raise ValueError(f"Unexpected source row count in {shard}")
    if files:
        raise ValueError(f"Unexpected vector file {min(files)}")
    report = {
        **MODEL,
        "source_revision": manifest["revision"],
        "shards": len(manifest["shards"]),
        "groups": groups,
        "articles": total,
        "nonblank": present,
        "blank": total - present,
        "dimensions": 768,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
