"""Restore the 168 original Fine News Parquet files and their frozen provenance."""

import argparse
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from huggingface_hub import HfApi, hf_hub_download

PROVENANCE_SHA256 = "64099e7dfd6ba98b0a9e086aed21f0ab17f86a1bd94875bf4bc817a63a8ef4cc"


def restore(output: Path) -> None:
    """Hydrate all verified source shards into a fresh directory."""
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        scratch = Path(temporary)
        tree = scratch / "source"
        tree.mkdir()
        provenance = tree / "provenance.json"
        HfApi().download_bucket_files(
            "marcusinthesky/CCFinance",
            [("recovery/ccfinance-v1/source-provenance.json", provenance)],
            raise_on_missing_files=True,
        )
        payload = provenance.read_bytes()
        if hashlib.sha256(payload).hexdigest() != PROVENANCE_SHA256:
            raise ValueError("Unexpected source provenance")
        manifest = json.loads(payload)

        def restore_shard(row: dict) -> None:
            rel = row["path"]
            target = tree / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=scratch) as download:
                path = Path(
                    hf_hub_download(
                        manifest["repository"],
                        rel,
                        repo_type="dataset",
                        revision=manifest["revision"],
                        local_dir=download,
                    )
                )
                with path.open("rb") as handle:
                    if (
                        path.stat().st_size != row["bytes"]
                        or hashlib.file_digest(handle, "sha256").hexdigest()
                        != row["sha256"]
                    ):
                        raise ValueError(f"Unexpected source content for {rel}")
                if path.is_symlink():
                    shutil.copyfile(path, target)
                else:
                    path.rename(target)

        with ThreadPoolExecutor(max_workers=3) as pool:
            for _ in pool.map(restore_shard, manifest["shards"]):
                pass
        tree.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    restore(parser.parse_args().output)
