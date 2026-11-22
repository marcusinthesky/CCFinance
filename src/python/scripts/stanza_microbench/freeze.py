"""Freeze a publication-year-balanced sample of Fine News leads."""

import argparse
import hashlib
import itertools
import json
import re
from pathlib import Path

import duckdb

YEARS = range(2019, 2024)
SALT = "stanza-microbench-v1:"
SNAPSHOT = "3168f32f57107eac95a2c53f024e5e340c91ef2e"
RAW_DVC_HASH = "3cd438d50a74f30d54d6eb854642e69b.dir"
ARTICLES_DVC_HASH = "401d21de164386c0e17c667f8b924ae8.dir"
COUNT = 8


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write newline-delimited UTF-8 JSON."""
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    """Rank the eligible IDs before retrieving the original text."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/fine-news"))
    parser.add_argument(
        "--articles",
        type=Path,
        default=Path("data/processed/articles/articles.parquet"),
    )
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    provenance = json.loads((args.raw / "provenance.json").read_text())
    if provenance.get("revision") != SNAPSHOT:
        raise ValueError("Raw source provenance does not identify the frozen snapshot")

    args.work.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        rank = con.execute(
            """WITH eligible AS (
                SELECT id, year(published) AS year, host, published,
                    sha256(? || id) AS rank_hash
                FROM read_parquet(?) WHERE canonical AND usable
                    AND year(published) BETWEEN 2019 AND 2023
            )
            SELECT *, row_number() OVER ranks AS year_rank,
                count(*) OVER (PARTITION BY year) AS frame_size
            FROM eligible
            WINDOW ranks AS (PARTITION BY year ORDER BY rank_hash, id)
            QUALIFY year_rank <= ?
            ORDER BY year, year_rank""",
            [SALT, str(args.articles), COUNT],
        ).fetchall()
        if [row[1] for row in rank] != [year for year in YEARS for _ in range(COUNT)]:
            raise ValueError("Each publication-year stratum must supply eight articles")
        ids = [row[0] for row in rank]
        if len(set(ids)) != len(ids):
            raise ValueError("Sample contains a duplicate article ID")
        files = con.execute(
            """SELECT DISTINCT filename FROM read_parquet(?)
            WHERE id IN (SELECT unnest(?))""",
            [str(args.raw / "*" / "eng_Latn" / "*.parquet"), ids],
        ).fetchall()
        bodies = con.execute(
            """SELECT id, text, filename FROM read_parquet(?)
            WHERE id IN (SELECT unnest(?))""",
            [[row[0] for row in files], ids],
        ).fetchall()
        if len(bodies) != len(ids) or {row[0] for row in bodies} != set(ids):
            raise ValueError("Sample IDs do not resolve one-to-one in raw source")
        by_id = {identifier: (text, filename) for identifier, text, filename in bodies}
        passages = []
        for identifier, year, host, published, rank_hash, year_rank, size in rank:
            text, filename = by_id[identifier]
            words = list(itertools.islice(re.finditer(r"\S+", text or ""), 150))
            if not words:
                raise ValueError(f"Selected article {identifier} has no words")
            end = words[-1].end()
            lead = text[:end]
            passages.append(
                {
                    "id": identifier,
                    "year": year,
                    "year_rank": year_rank,
                    "rank_sha256": rank_hash,
                    "frame_size": size,
                    "host": host,
                    "published": str(published),
                    "shard": str(Path(filename).relative_to(args.raw)),
                    "source_revision": SNAPSHOT,
                    "raw_dvc_hash": RAW_DVC_HASH,
                    "articles_dvc_hash": ARTICLES_DVC_HASH,
                    "text_sha256": hashlib.sha256(lead.encode()).hexdigest(),
                    "end": end,
                    "words": len(words),
                    "text": lead,
                }
            )
        write_jsonl(args.work / "passages.jsonl", passages)
        write_jsonl(
            args.work / "repeat-passages.jsonl",
            [row for row in passages if row["year_rank"] <= 2],
        )
        write_jsonl(
            args.manifest,
            [
                {key: value for key, value in row.items() if key != "text"}
                for row in passages
            ],
        )
        (args.work / "gliner-input").mkdir(exist_ok=True)
        source = con.from_query(
            "SELECT id, text FROM read_json_auto(?) ORDER BY year, year_rank",
            params=[str(args.work / "passages.jsonl")],
        )
        source.write_parquet(str(args.work / "gliner-input" / "passages.parquet"))


if __name__ == "__main__":
    main()
