"""Prepare a reproducible, source-verified sample for local extraction benchmarks."""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import duckdb
from pipeline.stages.processed.experiments.article_scoring import _BodyReader, _frame


def main() -> None:
    """Read sampled source bodies and preserve their candidate evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument(
        "--selection",
        type=Path,
        help="Reuse an existing selection and its adjacent JSON manifest",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    selection = args.output / "selection.parquet"
    sample = args.output / "articles.jsonl"
    if sample.exists():
        raise FileExistsError(sample)
    if args.selection:
        if selection.exists() or selection.with_suffix(".json").exists():
            raise FileExistsError(selection)
        shutil.copyfile(args.selection, selection)
        shutil.copyfile(
            args.selection.with_suffix(".json"), selection.with_suffix(".json")
        )
    source = Path("data/raw/fine-news")
    index = Path("data/processed/experiments/article-labels/candidates")
    started = time.monotonic()
    reading = 0.0
    count = 0
    with (
        _frame(index, args.size, args.seed, selection) as (
            batches,
            population,
            requested,
        ),
        duckdb.connect() as con,
        sample.open("x", encoding="utf-8") as output,
    ):
        reader = _BodyReader(source, con)
        for batch in batches:
            begin = time.monotonic()
            bodies = reader.read(batch)
            reading += time.monotonic() - begin
            for article in batch:
                value = article.model_dump(mode="json")
                value["text"] = bodies[article.article_id].text
                output.write(json.dumps(value, ensure_ascii=False) + "\n")
                count += 1
    if count != requested:
        raise ValueError(f"Sample has {count} records, expected {requested}")
    with sample.open("rb") as sample_file, selection.open("rb") as selection_file:
        sample_digest = hashlib.file_digest(sample_file, "sha256").hexdigest()
        selection_digest = hashlib.file_digest(selection_file, "sha256").hexdigest()
    manifest = {
        "population": population,
        "sample_size": count,
        "seed": args.seed,
        "selection": "SHA256(seed:article_id) retained-row priority",
        "sample_sha256": sample_digest,
        "selection_sha256": selection_digest,
        "source_body_read_seconds": reading,
        "source_row_groups_read": reader.groups_read,
        "total_preparation_seconds": time.monotonic() - started,
    }
    (args.output / "sample.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
