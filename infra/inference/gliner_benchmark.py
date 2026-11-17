"""Measure full-document GLiNER extraction on a prepared article sample."""

import argparse
import gzip
import json
import time
from pathlib import Path

import torch
from gliner_runtime import load_model
from gliner_schema import build_schema


def main() -> None:
    """Run one isolated model configuration and save timings and predictions."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--buffer-size", type=int)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--torch-threads", type=int)
    parser.add_argument("--chunk-size", type=int, default=384)
    parser.add_argument("--chunk-overlap", type=int, default=64)
    parser.add_argument("--batched-attributes", action="store_true")
    parser.add_argument("--gpu-memory-fraction", type=float, default=0.8)
    parser.add_argument(
        "--precision",
        choices=["fp32", "fp16", "bf16", "int8", "fp8", "nvfp4"],
        default="fp32",
    )
    parser.add_argument(
        "--backend",
        choices=[
            "standard",
            "compiled",
            "disentangled_flash",
            "disentangled_flash_heads",
        ],
        default="standard",
    )
    args = parser.parse_args()
    if not 0 < args.gpu_memory_fraction <= 1:
        raise ValueError("GPU memory fraction must be in (0, 1]")
    if args.batch_size < 1 or args.workers < 0:
        raise ValueError("Batch size must be positive and worker count nonnegative")
    buffer_size = args.batch_size if args.buffer_size is None else args.buffer_size
    if buffer_size < 1:
        raise ValueError("Buffer size must be positive")
    if not 0 <= args.chunk_overlap < args.chunk_size:
        raise ValueError(
            "Chunk overlap must be nonnegative and smaller than chunk size"
        )
    if args.torch_threads is not None:
        torch.set_num_threads(args.torch_threads)
    torch.cuda.set_per_process_memory_fraction(args.gpu_memory_fraction)
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    with args.sample.open(encoding="utf-8") as stream:
        articles = [
            json.loads(line) for _, line in zip(range(args.limit), stream, strict=False)
        ]
    if len(articles) != args.limit:
        raise ValueError(f"Expected {args.limit} articles; got {len(articles)}")
    read_seconds = time.perf_counter() - start
    start = time.perf_counter()
    model, model_metadata = load_model(
        args.model,
        args.precision,
        args.backend,
        batched_attributes=args.batched_attributes,
    )
    schema = build_schema(model)
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - start
    start = time.perf_counter()
    model.batch_extract_long(
        [item["text"] for item in articles[: min(args.batch_size, len(articles))]],
        schema,
        batch_size=args.batch_size,
        num_workers=args.workers,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        include_spans=True,
        include_confidence=True,
    )
    torch.cuda.synchronize()
    warmup_seconds = time.perf_counter() - start
    start = time.perf_counter()
    output = args.output / "predictions.jsonl.gz"
    invalid_spans = 0
    invalid_articles = 0
    corrected_spans = 0
    corrected_articles = 0
    with gzip.open(output, "wt", encoding="utf-8") as stream:
        for offset in range(0, len(articles), buffer_size):
            batch = articles[offset : offset + buffer_size]
            predictions = model.batch_extract_long(
                [item["text"] for item in batch],
                schema,
                batch_size=args.batch_size,
                num_workers=args.workers,
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
                include_spans=True,
                include_confidence=True,
            )
            if len(predictions) != len(batch):
                raise ValueError("Prediction count does not match the input batch")
            for article, prediction in zip(batch, predictions, strict=True):
                errors = []
                corrected = 0
                for entity in prediction.get("entities", {}).get("company", []):
                    span_start, span_end = entity["start"], entity["end"]
                    corrected += bool(entity.get("synthetic_suffix_removed"))
                    if (
                        entity.get("invalid_window_span")
                        or not (0 <= span_start < span_end <= len(article["text"]))
                        or article["text"][span_start:span_end] != entity["text"]
                    ):
                        errors.append(
                            {
                                "start": span_start,
                                "end": span_end,
                                "predicted": entity["text"],
                                "source": article["text"][span_start:span_end],
                            }
                        )
                invalid_spans += len(errors)
                invalid_articles += bool(errors)
                corrected_spans += corrected
                corrected_articles += bool(corrected)
                stream.write(
                    json.dumps(
                        {
                            "article_id": article["article_id"],
                            "status": "invalid_span" if errors else "ok",
                            "span_errors": errors,
                            "prediction": prediction,
                        }
                    )
                    + "\n"
                )
    torch.cuda.synchronize()
    seconds = time.perf_counter() - start
    report = {
        "configuration": vars(args)
        | {"sample": str(args.sample), "output": str(args.output)},
        "articles": len(articles),
        "valid_articles": len(articles) - invalid_articles,
        "invalid_span_articles": invalid_articles,
        "invalid_spans": invalid_spans,
        "synthetic_suffix_corrected_articles": corrected_articles,
        "synthetic_suffix_corrected_spans": corrected_spans,
        "sample_read_seconds": read_seconds,
        "model_load_seconds": load_seconds,
        "warmup_seconds": warmup_seconds,
        "inference_and_output_seconds": seconds,
        "articles_per_second": len(articles) / seconds,
        "valid_articles_per_second": (len(articles) - invalid_articles) / seconds,
        "peak_cuda_memory_bytes": torch.cuda.max_memory_allocated(),
        "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
        "torch_version": torch.__version__,
        "gpu": torch.cuda.get_device_name(),
        "model": model_metadata,
        "torch_threads": torch.get_num_threads(),
        "long_document_handling": "Overlapping word windows with GLiNER2 merge",
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
