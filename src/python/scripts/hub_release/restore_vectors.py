# /// script
# requires-python = ">=3.13,<3.14"
# dependencies = ["pyarrow==26.0.0"]
# ///
"""Restore the frozen EmbeddingGemma DVC output from the public CCFinance release."""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[4]
BASE = "https://huggingface.co/datasets/marcusinthesky/CCFinance/resolve/524d04acec2ed7dfc5b76cfb09fae9e57850b062"
SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("embedding", pa.list_(pa.float16(), 768)),
        ("has_text", pa.bool_()),
    ],
    metadata={
        "model": "google/embeddinggemma-300m",
        "revision": "57c266a740f537b4dc058e1b0cda161fd15afa75",
        "max_tokens": "2048",
        "prefix": "title: none | text: ",
    },
)


def fetch(name: str, target: Path) -> None:
    """Fetch a file from the pinned public release with transient retries."""
    subprocess.run(  # noqa: S603 - fixed command and hash-verified release paths
        [  # noqa: S607 - curl is supplied by the pinned shell
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--retry",
            "4",
            "--output",
            str(target),
            f"{BASE}/{name}",
        ],
        check=True,
    )


def digest(path: Path, algorithm: str) -> str:
    """Hash a serialized artifact without loading it into memory."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, algorithm).hexdigest()


def restore(output: Path) -> None:
    """Recreate the original vector groups and verify every DVC object hash."""
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    with (ROOT / "data/inputs/body-vectors/groups.csv").open() as handle:
        for row in csv.DictReader(handle):
            path = Path(row["path"])
            groups[f"{path.parts[0]}-{path.parent.stem}"].append(row)
    with TemporaryDirectory(dir=output.parent) as staging:
        scratch = Path(staging)
        tree = scratch / "vectors"
        tree.mkdir()
        manifest = scratch / "manifest.json"
        fetch("documentation/manifest.json", manifest)
        if (
            digest(manifest, "sha256")
            != "c734c8f7adb5892a4cda925fb4903ce4c7a09cb358670865d07123cb8355035e"
        ):
            raise ValueError("Unexpected release manifest")
        parts = defaultdict(list)
        for entry in json.loads(manifest.read_text())["files"]:
            parts[Path(entry["path"]).stem.rsplit("-", 1)[0]].append(entry)
        if parts.keys() != groups.keys():
            raise ValueError("Source inventory differs from the released vectors")

        def restore_part(key: str) -> None:
            rows = iter(groups[key])
            for entry in sorted(parts[key], key=lambda item: item["path"]):
                shard = scratch / Path(entry["path"]).name
                fetch(entry["path"], shard)
                if digest(shard, "sha256") != entry["sha256"]:
                    raise ValueError(f"Invalid Hub shard {shard.name}")
                table = (
                    pq.ParquetFile(shard)
                    .read(columns=SCHEMA.names)
                    .cast(SCHEMA)
                    .combine_chunks()
                )
                offset = 0
                while offset < table.num_rows:
                    group = next(rows)
                    size = int(group["rows"])
                    target = tree / group["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with pq.ParquetWriter(
                        target, SCHEMA, use_dictionary=False
                    ) as writer:
                        for batch in table.slice(offset, size).to_batches(
                            max_chunksize=32
                        ):
                            writer.write_table(
                                pa.Table.from_batches([batch], schema=SCHEMA)
                            )
                    if digest(target, "md5") != group["md5"]:
                        raise ValueError(f"Restored hash differs for {group['path']}")
                    offset += size
                shard.unlink()
            if next(rows, None) is not None:
                raise ValueError(f"Missing released rows for {key}")

        with ThreadPoolExecutor(max_workers=4) as pool:
            for _ in pool.map(restore_part, sorted(parts)):
                pass
        (tree / ".lock").touch()
        tree.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    restore(parser.parse_args().output)
