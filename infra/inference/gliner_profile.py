"""Profile warmed extraction; profiler timings are not throughput measurements."""

import argparse
import cProfile
import json
import pstats
from pathlib import Path

import torch
from gliner2 import AutoExtractor
from gliner_schema import build_schema


def main() -> None:
    """Attribute CPU calls and CUDA operators for a small, warmed real sample."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--backend", choices=["compiled", "disentangled_flash"], default="compiled"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with args.sample.open(encoding="utf-8") as stream:
        texts = [
            json.loads(line)["text"]
            for _, line in zip(range(args.limit), stream, strict=False)
        ]
    model = AutoExtractor.from_pretrained(
        "/model",
        map_location="cuda",
        quantize=True,
        compile=args.backend == "compiled",
        attention_backend="disentangled_flash"
        if args.backend == "disentangled_flash"
        else "standard",
    )
    schema = build_schema(model)

    def extract() -> list[dict]:
        return model.batch_extract_long(
            texts,
            schema,
            batch_size=args.batch_size,
            include_spans=True,
            include_confidence=True,
        )

    extract()
    torch.cuda.synchronize()
    calls = cProfile.Profile()
    with torch.profiler.profile(
        activities=[
            torch.profiler.ProfilerActivity.CPU,
            torch.profiler.ProfilerActivity.CUDA,
        ]
    ) as profile:
        calls.enable()
        extract()
        torch.cuda.synchronize()
        calls.disable()
    calls.dump_stats(args.output / "calls.prof")
    with (args.output / "cpu-functions.txt").open("w") as stream:
        pstats.Stats(calls, stream=stream).sort_stats("cumulative").print_stats(50)
    for name, key in (
        ("cpu-operators", "self_cpu_time_total"),
        ("cuda-operators", "self_device_time_total"),
    ):
        (args.output / f"{name}.txt").write_text(
            profile.key_averages().table(sort_by=key, row_limit=40) + "\n"
        )
    print("Profile saved; use unprofiled benchmark runs for throughput.")


if __name__ == "__main__":
    main()
