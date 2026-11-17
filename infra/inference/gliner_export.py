"""Collect local benchmark evidence without copying source article bodies."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    """Return the file's SHA-256 digest."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    """Copy selections, predictions, reports, logs, and the executing code."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    runtime = Path(".runtime/gliner-benchmark")
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ("sample", "pilot-1000"):
        destination = args.output / name
        destination.mkdir()
        for filename in ("selection.parquet", "selection.json", "sample.json"):
            shutil.copy2(runtime / name / filename, destination / filename)
    with (runtime / "screen.jsonl").open(encoding="utf-8") as stream:
        ids = [json.loads(line)["article_id"] for line in stream]
    (args.output / "screen-article-ids.json").write_text(
        json.dumps(ids, indent=2) + "\n"
    )
    for name in (
        "screen-results",
        "screen-logs",
        "batch-results",
        "batch-logs",
        "final-results",
        "final-logs",
        "throughput-results",
        "throughput-logs",
        "profile-compiled",
        "precision-probes",
        "throughput-code",
        "buffer-batch-results",
        "buffer-batch-logs",
        "optimized-trials",
        "buffer-final-results",
        "buffer-final-logs",
        "attribute-trials",
        "window-logs",
    ):
        shutil.copytree(runtime / name, args.output / name)
    for name in (
        "invalid-span-repro",
        "invalid-span-corrected",
        "small-fp16-flash-b64-full-2",
    ):
        ignore = (
            shutil.ignore_patterns("report.json")
            if name == "invalid-span-repro"
            else None
        )
        shutil.copytree(
            runtime / "results" / name,
            args.output / "earlier-runs" / name,
            ignore=ignore,
        )
    shutil.copy2(runtime / "device-check.log", args.output / "device-check.log")
    logs = args.output / "logs"
    logs.mkdir()
    for file in runtime.glob("*.log"):
        shutil.copy2(file, logs / file.name)
    for filename in ("metrics.json", "throughput.csv"):
        shutil.copy2(runtime / filename, args.output / filename)
    code = args.output / "code"
    code.mkdir()
    shutil.copytree(runtime / "historical-launchers", code / "historical-launchers")
    for file in sorted(Path("infra/inference").glob("gliner*")):
        if file.is_file():
            shutil.copy2(file, code / file.name)
    shutil.copy2(
        Path(
            "src/python/apps/pipeline/src/pipeline/stages/processed/experiments/article_scoring.py"
        ),
        code / "source_article_scoring.py",
    )
    weights = {
        name: sha256(Path(".runtime/models") / name / "model.safetensors")
        for name in ("gliner2.5-small-v1", "gliner2.5-base-v1")
    }
    manifest = {
        "image": (
            "lmsysorg/sglang@sha256:"
            "f7876bef696ccf9cf75a2bf7ccb82970f5fac577f082fb8ca95c9a59d2160eb5"
        ),
        "models": {
            "gliner2.5-small-v1": {
                "revision": "b5d42bf7dc7d01c40304ae4ed43c2f13c325a75b",
                "weights_sha256": weights["gliner2.5-small-v1"],
            },
            "gliner2.5-base-v1": {
                "revision": "07d99c0ba5d15cb3b24e0a236fa99bdd4ef87a5c",
                "weights_sha256": weights["gliner2.5-base-v1"],
            },
        },
        "code_sha256": {
            str(file.relative_to(code)): sha256(file)
            for file in sorted(code.rglob("*"))
            if file.is_file()
        },
        "article_bodies_included": False,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
