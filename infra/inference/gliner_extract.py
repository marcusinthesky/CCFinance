"""Extract core financial-news metadata from Parquet articles by row group.

Row groups run in a seeded random order, so any completed prefix is a random
cluster sample. Completed outputs are skipped, so rerunning resumes the work.
"""

import argparse
import hashlib
import json
import math
import os
import random
import tempfile
import time
from pathlib import Path

import duckdb
import torch
from gliner2.inference.chunking import merge_chunk_results, split_text_into_chunks
from gliner2.inference.schema import Schema
from gliner2.models.boundary.engine import BoundaryExtractor
from gliner_probabilities import capture_probabilities
from gliner_runtime import load_model
from gliner_schema import (
    ARTICLE_FORMS,
    ATTRIBUTES,
    ENTITIES,
    EVENT_FAMILIES,
    build_schema,
)

WINDOW = (
    "STRUCT(start INTEGER, stop INTEGER, article_form FLOAT[], event_family FLOAT[])"
)
ARTICLES = {
    "id": "VARCHAR",
    "text_sha256": "VARCHAR",
    "status": "VARCHAR",
    "n_windows": "INTEGER",
    "article_form": "VARCHAR",
    "windows": f"{WINDOW}[]",
}
MENTIONS = {
    "id": "VARCHAR",
    "entity_type": "VARCHAR",
    "text": "VARCHAR",
    "start": "INTEGER",
    "stop": "INTEGER",
    "confidence": "FLOAT",
} | dict.fromkeys(ATTRIBUTES, "FLOAT[]")
CODE = ("extract", "schema", "runtime", "attributes", "probabilities")


def sha256(path: Path) -> str:
    """Hash a file without loading it into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def span_errors(prediction: dict, window: str) -> int:
    """Count spans that differ from their window, allowing GLiNER's added full stop."""
    errors = 0
    for items in prediction.get("entities", {}).values():
        for item in items:
            start, stop, text = item["start"], item["end"], item["text"]
            synthetic = stop == len(window) + 1 and text == window[start:] + "."
            matches = 0 <= start < stop <= len(window) and window[start:stop] == text
            errors += not (synthetic or matches)
    return errors


def distribution(values: list[float], *, softmax: bool) -> bool:
    """Check finite probabilities; softmax scores must also sum to one."""
    valid = all(math.isfinite(x) and 0 <= x <= 1 for x in values)
    return valid and (not softmax or math.isclose(sum(values), 1, abs_tol=0.001))


def extract(
    model: BoundaryExtractor,
    schema: Schema,
    rows: list[tuple[str, str, str]],
    args: argparse.Namespace,
) -> tuple[list[dict], list[dict]]:
    """Extract windows in GPU batches, then merge articles and flatten mentions."""
    splitter = model.processor.word_splitter
    chunks = [
        split_text_into_chunks(text, args.chunk_size, args.chunk_overlap, splitter)
        for _, text, _ in rows
    ]
    windows = [chunk.text for group in chunks for chunk in group]
    predictions = model.batch_extract(
        windows,
        schema,
        batch_size=args.batch_size,
        num_workers=args.workers,
        include_spans=True,
        include_confidence=True,
    )
    if len(predictions) != len(windows):
        raise ValueError("Window count differs from prediction count")
    articles, mentions, offset = [], [], 0
    for (identifier, text, digest), group in zip(rows, chunks, strict=True):
        results = predictions[offset : offset + len(group)]
        offset += len(group)
        valid, evidence = True, []
        for chunk, prediction in zip(group, results, strict=True):
            scores = prediction.pop("_class_probabilities")
            form = [scores["article_form"]["values"][x] for x in ARTICLE_FORMS]
            events = [scores["event_family"]["values"][x] for x in EVENT_FAMILIES]
            valid &= span_errors(prediction, chunk.text) == 0
            valid &= distribution(form, softmax=True)
            valid &= distribution(events, softmax=False)
            evidence.append(
                {
                    "start": chunk.start_char,
                    "stop": chunk.end_char,
                    "article_form": form,
                    "event_family": events,
                }
            )
        merged = merge_chunk_results(
            text, group, results, include_spans=True, include_confidence=True
        )
        for entity_type, items in merged.get("entities", {}).items():
            for item in items:
                row = {
                    "id": identifier,
                    "entity_type": entity_type,
                    "text": item["text"],
                    "start": item["start"],
                    "stop": item["end"],
                    "confidence": item["confidence"],
                }
                for name, labels in ATTRIBUTES.items():
                    probabilities = item.get(name, {}).get("probabilities")
                    row[name] = probabilities and [probabilities[x] for x in labels]
                    valid &= not row[name] or distribution(row[name], softmax=True)
                mentions.append(row)
        articles.append(
            {
                "id": identifier,
                "text_sha256": digest,
                "status": "ok" if valid else "invalid",
                "n_windows": len(group),
                "article_form": (merged.get("article_form") or {}).get("label"),
                "windows": evidence,
            }
        )
    return articles, mentions


def write(
    con: duckdb.DuckDBPyConnection,
    rows: list[dict],
    columns: dict[str, str],
    target: Path,
) -> None:
    """Write rows with explicit column types, then publish the file atomically."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        lines, parquet = Path(staging) / "rows.jsonl", Path(staging) / target.name
        lines.write_text("".join(json.dumps(row) + "\n" for row in rows))
        types = ", ".join(f"'{name}': '{kind}'" for name, kind in columns.items())
        con.execute(
            f"""COPY (SELECT * FROM read_json('{lines}', columns={{{types}}},
                format='newline_delimited')) TO '{parquet}' (COMPRESSION zstd)"""  # noqa: S608
        )
        os.replace(parquet, target)


def main() -> None:
    """Extract every pending row group, recording the contract and progress."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=Path("/model"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--buffer-size", type=int, default=8192)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=384)
    parser.add_argument("--chunk-overlap", type=int, default=64)
    args = parser.parse_args()
    con = duckdb.connect()
    sources = [str(path) for path in sorted(args.source.rglob("*.parquet"))]
    # Each unit is one row group: (file, first row, row count).
    units = con.execute(
        """WITH groups AS (
            SELECT DISTINCT file_name, row_group_id, row_group_num_rows AS n
            FROM parquet_metadata(?)
        ) SELECT file_name, row_group_id,
            sum(n) OVER (PARTITION BY file_name ORDER BY row_group_id) - n, n
        FROM groups ORDER BY ALL""",
        [sources],
    ).fetchall()
    random.Random(args.seed).shuffle(units)  # noqa: S311 - reproducible order.
    done = args.output / "articles"

    def name(file: str, group: int) -> str:
        relative = Path(file).relative_to(args.source).with_suffix("")
        return f"{str(relative).replace('/', '--')}--{group:03d}.parquet"

    pending = [unit for unit in units if not (done / name(*unit[:2])).exists()]
    print(f"{len(pending)} of {len(units)} row groups pending", flush=True)
    if not pending:
        return
    torch.cuda.set_per_process_memory_fraction(0.8)
    started = time.perf_counter()
    model = load_model(str(args.model))
    capture_probabilities(model)
    schema = build_schema(model)
    contract = {
        "configuration": {key: str(value) for key, value in vars(args).items()},
        "schema": schema.build(),
        "labels": {
            "entities": list(ENTITIES),
            **ATTRIBUTES,
            "article_form": list(ARTICLE_FORMS),
            "event_family": list(EVENT_FAMILIES),
        },
        "model_sha256": sha256(args.model / "model.safetensors"),
        "code_sha256": {
            part: sha256(Path(__file__).with_name(f"gliner_{part}.py")) for part in CODE
        },
    }
    contract = json.loads(json.dumps(contract))
    recorded = args.output / "schema.json"
    if recorded.exists() and json.loads(recorded.read_text()) != contract:
        raise ValueError(f"{recorded} differs from this run; use a new output")
    args.output.mkdir(parents=True, exist_ok=True)
    recorded.write_text(json.dumps(contract, indent=2) + "\n")
    total = sum(unit[3] for unit in units)
    session = {"articles": 0, "invalid": 0, "seconds": 0.0}
    for index, (file, group, first, count) in enumerate(pending):
        rows = con.execute(
            """SELECT id, text, sha256(text) FROM read_parquet(?, file_row_number=true)
            WHERE file_row_number >= ? AND file_row_number < ?
            ORDER BY file_row_number""",
            [file, first, first + count],
        ).fetchall()
        if len(rows) != count:
            raise ValueError(f"{file} row group {group}: {len(rows)} of {count} rows")
        if index == 0:
            warmup = time.perf_counter()
            extract(model, schema, rows[: args.batch_size], args)
            torch.cuda.synchronize()
            session["load_seconds"] = warmup - started
            session["warmup_seconds"] = time.perf_counter() - warmup
        begin = time.perf_counter()
        articles, mentions = [], []
        for offset in range(0, len(rows), args.buffer_size):
            batch = rows[offset : offset + args.buffer_size]
            batch_articles, batch_mentions = extract(model, schema, batch, args)
            articles += batch_articles
            mentions += batch_mentions
        # Articles mark completion, so they are published after their mentions.
        unit = name(file, group)
        write(con, mentions, MENTIONS, args.output / "mentions" / unit)
        write(con, articles, ARTICLES, done / unit)
        session["seconds"] += time.perf_counter() - begin
        session["articles"] += len(articles)
        session["invalid"] += sum(article["status"] != "ok" for article in articles)
        units_done, articles_done = con.execute(
            "SELECT count(*), sum(num_rows) FROM parquet_file_metadata(?)",
            [str(done / "*.parquet")],
        ).fetchone()
        rate = session["articles"] / session["seconds"]
        progress = session | {
            "row_groups": len(units),
            "row_groups_done": units_done,
            "articles_total": total,
            "articles_done": articles_done,
            "articles_per_second": rate,
            "remaining_hours": (total - articles_done) / rate / 3600,
            "gpu": torch.cuda.get_device_name(),
            "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
        }
        (args.output / "progress.json").write_text(json.dumps(progress, indent=2))
        print(json.dumps({"unit": unit} | progress), flush=True)


if __name__ == "__main__":
    main()
