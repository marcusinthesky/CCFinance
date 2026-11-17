"""Evaluate joint financial-news metadata on a small source-verified sample."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import torch
from gliner2.inference.chunking import (
    merge_chunk_results,
    remap_result_spans,
    split_text_into_chunks,
)
from gliner_export import sha256
from gliner_probabilities import capture_probabilities
from gliner_runtime import load_model
from gliner_schema import (
    build_metadata_schema,
    build_schema,
    build_transaction_schema,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


# Authored challenge cases diagnose specific behaviors; they are not a
# representative accuracy benchmark or substitutes for human news annotations.
CHALLENGES = {
    "conditional-acquisition": (
        "Apple agreed to acquire Intel for $2 billion, subject to regulatory approval.",
        "Apple is acquirer; Intel is target; agreement does not mean completion.",
    ),
    "negated-acquisition": (
        "Apple did not acquire Intel. Both companies denied reports of a deal.",
        "An acquisition is negated, not completed.",
    ),
    "opposing-sentiment": (
        "Microsoft reported record profits and raised its outlook. Intel reported "
        "record losses and warned that it might go bankrupt.",
        "Microsoft positive and Intel negative in their respective contexts.",
    ),
    "two-transactions": (
        "Apple acquired Beats for $3 billion. Microsoft acquired LinkedIn for "
        "$26.2 billion.",
        "Keep Apple/Beats/$3 billion separate from Microsoft/LinkedIn/$26.2 billion.",
    ),
    "person-place": (
        "Rodrigo Duterte spoke at a rally in Manila, the capital of the Philippines.",
        "Duterte is a person; Manila and Philippines are places; no named company.",
    ),
    "generic-aliases": (
        "People want new news. The target price for lunch is ten dollars.",
        "No named company; common alias words do not establish a business mention.",
    ),
    "regulator": (
        "The US Securities and Exchange Commission fined Tesla $20 million "
        "for misleading investors.",
        "The SEC is a public body; Tesla is the company affected by the fine.",
    ),
    "analyst-source": (
        "A Goldman Sachs analyst upgraded Apple to buy after strong iPhone sales.",
        "Goldman Sachs supplies the analyst; the recommendation concerns Apple.",
    ),
    "actual-forecast": (
        "Microsoft reported Q3 2025 revenue of $70 billion, versus $65 billion "
        "a year earlier. It forecast Q4 revenue of $75 billion.",
        "Keep actual Q3, historical Q3 and forecast Q4 values and periods distinct.",
    ),
    "press-release": (
        "PRESS RELEASE: Microsoft today announced that its board approved a "
        "$10 billion share repurchase program. This announcement is issued "
        "by Microsoft Investor Relations.",
        "Press release; approved repurchase authorization, not completed purchases.",
    ),
}


def spans(value: object, path: str = "") -> Iterator[tuple[str, dict]]:
    """Yield source-span dictionaries throughout entities and structured records."""
    if isinstance(value, dict):
        if {"text", "start", "end"} <= value.keys():
            yield path, value
        for key, child in value.items():
            yield from spans(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from spans(child, f"{path}[{index}]")


def label_record_choices(prediction: dict, definition: dict, text: str) -> None:
    """Keep enum labels separate from their upstream record-anchor coordinates."""
    for structure in definition.get("json_structures", []):
        for name, fields in structure.items():
            for record in prediction.get(name, []):
                for field, specification in fields.items():
                    if not isinstance(specification, dict) or not specification.get(
                        "choices"
                    ):
                        continue
                    value = record.get(field)
                    if not isinstance(value, dict):
                        continue
                    result = {"label": value["text"], "confidence": value["confidence"]}
                    if {"start", "end"} <= value.keys():
                        start, end = value["start"], value["end"]
                        result["support"] = {
                            "text": text[start:end],
                            "start": start,
                            "end": end,
                        }
                    record[field] = result


def score_errors(value: object, path: str = "") -> list[str]:
    """Check finite confidence ranges and normalized single-label attributes."""
    errors = []
    if isinstance(value, dict):
        confidence = value.get("confidence")
        if confidence is not None and (
            not math.isfinite(confidence) or not 0 <= confidence <= 1
        ):
            errors.append(f"{path}: invalid confidence")
        if "probabilities" in value:
            probabilities = list(value["probabilities"].values())
            if any(not math.isfinite(x) or not 0 <= x <= 1 for x in probabilities):
                errors.append(f"{path}: invalid attribute probability")
            if not math.isclose(sum(probabilities), 1, abs_tol=0.001):
                errors.append(f"{path}: attribute softmax does not sum to one")
            label = value["label"]
            if abs(value["confidence"] - value["probabilities"][label]) > 0.001:
                errors.append(f"{path}: selected attribute score differs")
        for key, child in value.items():
            errors.extend(score_errors(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(score_errors(child, f"{path}[{index}]"))
    return errors


def main() -> None:
    """Extract complete sampled articles and save window-level score evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="/model")
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--chunk-size", type=int, default=384)
    parser.add_argument("--chunk-overlap", type=int, default=64)
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=["baseline", "core", "events", "transactions"],
        default=["baseline", "core", "events"],
    )
    parser.add_argument(
        "--backend",
        choices=["disentangled_flash", "disentangled_flash_heads"],
        default="disentangled_flash_heads",
    )
    parser.add_argument("--precision", choices=["fp16", "fp32", "bf16"], default="fp16")
    args = parser.parse_args()
    if min(args.limit, args.batch_size, args.repetitions) < 1:
        raise ValueError("Sample, batch and repetition counts must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    with args.sample.open(encoding="utf-8") as stream:
        articles = [
            json.loads(line) for _, line in zip(range(args.limit), stream, strict=False)
        ]
    if len(articles) != args.limit:
        raise ValueError("The input sample is smaller than requested")
    selection = [
        {
            "article_id": article["article_id"],
            "text_sha256": hashlib.sha256(article["text"].encode()).hexdigest(),
        }
        for article in articles
    ]
    (args.output / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    for name, (text, expectation) in CHALLENGES.items():
        articles.append(
            {
                "article_id": f"challenge:{name}",
                "text": text,
                "expectation": expectation,
            }
        )
    torch.cuda.set_per_process_memory_fraction(0.8)
    model, metadata = load_model(
        args.model, args.precision, args.backend, batched_attributes=True
    )
    capture_probabilities(model)
    chunks = [
        split_text_into_chunks(
            x["text"],
            args.chunk_size,
            args.chunk_overlap,
            word_splitter=model.processor.word_splitter,
        )
        for x in articles
    ]
    texts = [chunk.text for group in chunks for chunk in group]
    reports = {}
    for profile in args.profiles:
        if profile == "baseline":
            schema = build_schema(model)
        elif profile == "transactions":
            schema = build_transaction_schema(model)
        else:
            schema = build_metadata_schema(model, records=profile == "events")
        definition = schema.build()
        directory = args.output / profile
        directory.mkdir()
        (directory / "schema.json").write_text(json.dumps(definition, indent=2) + "\n")
        print(f"Warming {profile}: {len(texts)} windows", flush=True)
        started = time.perf_counter()
        model.batch_extract(
            texts[: args.batch_size],
            schema,
            batch_size=args.batch_size,
            include_spans=True,
            include_confidence=True,
        )
        torch.cuda.synchronize()
        warmup = time.perf_counter() - started
        repetitions = []
        for _ in range(args.repetitions):
            started = time.perf_counter()
            predictions = model.batch_extract(
                texts,
                schema,
                batch_size=args.batch_size,
                include_spans=True,
                include_confidence=True,
            )
            torch.cuda.synchronize()
            repetitions.append(time.perf_counter() - started)
        inference = repetitions[-1]
        if len(predictions) != len(texts):
            raise ValueError("Window count differs from prediction count")
        offset = 0
        errors = []
        probability_errors = []
        counts = Counter()
        fallback = 0
        nonfinite = 0
        with gzip.open(
            directory / "predictions.jsonl.gz", "wt", encoding="utf-8"
        ) as output:
            for article, group in zip(articles, chunks, strict=True):
                window_predictions = predictions[offset : offset + len(group)]
                offset += len(group)
                windows = []
                article_errors = []
                for chunk, prediction in zip(group, window_predictions, strict=True):
                    classes = prediction.pop("_class_probabilities", {})
                    probability_errors.extend(score_errors(prediction))
                    for distribution in classes.values():
                        values = distribution["values"].values()
                        nonfinite += sum(
                            not math.isfinite(x) or not 0 <= x <= 1 for x in values
                        )
                        if distribution["activation"] == "softmax" and not math.isclose(
                            sum(values), 1, abs_tol=0.001
                        ):
                            probability_errors.append(
                                "Classification softmax does not sum to one"
                            )
                        if distribution["activation"] == "sigmoid":
                            fallback += max(values) < distribution["threshold"]
                    label_record_choices(prediction, definition, chunk.text)
                    for path, span in spans(prediction):
                        start, end = span["start"], span["end"]
                        synthetic = (
                            end == len(chunk.text) + 1
                            and span["text"] == chunk.text[start:] + "."
                        )
                        if not synthetic and (
                            not 0 <= start < end <= len(chunk.text)
                            or chunk.text[start:end] != span["text"]
                        ):
                            article_errors.append(
                                {
                                    "path": path,
                                    "start": start,
                                    "end": end,
                                    "text": span["text"],
                                }
                            )
                    windows.append(
                        {
                            "start": chunk.start_char,
                            "end": chunk.end_char,
                            "class_probabilities": classes,
                            "prediction": remap_result_spans(
                                prediction, article["text"], chunk
                            ),
                        }
                    )
                merged = merge_chunk_results(
                    article["text"],
                    group,
                    window_predictions,
                    include_spans=True,
                    include_confidence=True,
                )
                for entity_type, entities in merged.get("entities", {}).items():
                    counts[f"entities:{entity_type}"] += len(entities)
                    for entity in entities:
                        for name in (
                            "article_role",
                            "local_relevance",
                            "financial_sentiment",
                        ):
                            if name in entity:
                                counts[f"{name}:{entity[name]['label']}"] += 1
                for structure in definition.get("json_structures", []):
                    for name in structure:
                        counts[f"records:{name}"] += len(merged.get(name, []))
                errors.extend(
                    {"article_id": article["article_id"], **e} for e in article_errors
                )
                row = {
                    "article_id": article["article_id"],
                    "prediction": merged,
                    "windows": windows,
                    "span_errors": article_errors,
                }
                if "expectation" in article:
                    row.update(
                        {"text": article["text"], "expectation": article["expectation"]}
                    )
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
        report = {
            "source_articles": args.limit,
            "challenge_articles": len(CHALLENGES),
            "windows": len(texts),
            "warmup_seconds": warmup,
            "inference_seconds": inference,
            "inference_repetitions_seconds": repetitions,
            "articles_per_second": len(articles) / inference,
            "counts": dict(counts),
            "span_errors": errors,
            "multilabel_below_threshold_fallback_windows": fallback,
            "invalid_class_probabilities": nonfinite,
            "probability_errors": probability_errors,
        }
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        reports[profile] = report
        print(json.dumps({"profile": profile, **report}), flush=True)
    manifest = {
        "configuration": {
            **vars(args),
            "sample": str(args.sample),
            "output": str(args.output),
        },
        "model": metadata,
        "gpu": torch.cuda.get_device_name(),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        "torch_version": torch.__version__,
        "sample_sha256": sha256(args.sample),
        "model_weight_sha256": sha256(Path(args.model) / "model.safetensors"),
        "code_sha256": {
            name: sha256(Path(__file__).with_name(name))
            for name in (
                "gliner_metadata.py",
                "gliner_schema.py",
                "gliner_probabilities.py",
                "gliner_attributes.py",
                "gliner_runtime.py",
            )
        },
        "reports": reports,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
