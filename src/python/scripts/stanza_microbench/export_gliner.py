"""Save GLiNER's raw entity spans in the same row format as Stanza."""

import argparse
from pathlib import Path

import duckdb
from freeze import write_jsonl
from score import read_rows


def main() -> None:
    """Confirm all extraction rows are valid, then export spans including empty rows."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--passages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    passages = read_rows(args.passages)
    with duckdb.connect() as con:
        articles = con.execute(
            "SELECT id, text_sha256, status FROM read_parquet(?)",
            [str(args.source / "articles" / "*.parquet")],
        ).fetchall()
        mentions = con.execute(
            """
            SELECT id, start, stop, entity_type, text, confidence
            FROM read_parquet(?) ORDER BY id, start, stop, entity_type
            """,
            [str(args.source / "mentions" / "*.parquet")],
        ).fetchall()
    if len(articles) != len(passages) or {row[0] for row in articles} != set(passages):
        raise ValueError("GLiNER results do not cover the frozen sample")
    for key, digest, status in articles:
        if status != "ok" or digest != passages[key]["text_sha256"]:
            raise ValueError(f"Invalid GLiNER extraction for {key}: {status}")
    rows = {
        key: {"id": key, "text_sha256": info["text_sha256"], "spans": []}
        for key, info in passages.items()
    }
    for key, start, end, label, text, probability in mentions:
        if text != passages[key]["text"][start:end]:
            raise ValueError(f"GLiNER span does not match the original text for {key}")
        rows[key]["spans"].append(
            {
                "start": start,
                "end": end,
                "text": text,
                "type": label,
                "confidence": probability,
            }
        )
    write_jsonl(args.output, list(rows.values()))


if __name__ == "__main__":
    main()
