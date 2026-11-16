"""Prepare probability samples and acquire publisher-matched Parquet row groups."""

import json
import random
import re
from collections.abc import Iterator
from contextlib import contextmanager
from fnmatch import fnmatchcase
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Annotated

import duckdb
import httpx
import typer
from huggingface_hub import HfApi, hf_hub_url

from pipeline.experiments.source_comparison import (
    Draw,
    DrawCounts,
    FileRecord,
    Manifest,
    SampleCounts,
    load_config,
)
from pipeline.stages.raw.publishers import SOURCES, extract_group


@contextmanager
def stage_output(output: Path) -> Iterator[Path]:
    """Publish a complete stage directory once, preserving existing outputs."""
    if output.exists():
        raise FileExistsError(f"Output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "output"
        staging.mkdir()
        yield staging
        staging.rename(output)


def hub_path(source: str) -> tuple[str, str, str]:
    """Split a pinned dataset URI into repository, commit and relative path."""
    if not source.startswith("hf://datasets/"):
        raise ValueError("Expected an hf://datasets/ URI at a pinned commit")
    owner, repository, path = source.removeprefix("hf://datasets/").split("/", 2)
    name, revision = repository.rsplit("@", 1)
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Source revisions must be immutable 40-character commits")
    return f"{owner}/{name}", revision, path


def source_files(source: str) -> list[FileRecord]:
    """List native files and stored sizes without downloading their contents."""
    repository, revision, pattern = hub_path(source)
    info = HfApi(token=False).dataset_info(
        repository, revision=revision, files_metadata=True
    )
    files = []
    for entry in info.siblings or []:
        if fnmatchcase(entry.rfilename, pattern):
            if entry.size is None or entry.blob_id is None:
                raise ValueError(f"Incomplete file metadata: {entry.rfilename}")
            files.append(
                FileRecord(
                    file=f"hf://datasets/{repository}@{revision}/{entry.rfilename}",
                    size=entry.size,
                    identity=entry.lfs.sha256 if entry.lfs else entry.blob_id,
                )
            )
    if not files:
        raise ValueError(f"No native Parquet files matched {source}")
    return sorted(files, key=lambda entry: entry.file)


def check_range(file: FileRecord) -> int:
    """Verify an eight-byte range response and return the Parquet footer size."""
    repository, revision, path = hub_path(file.file)
    url = hf_hub_url(repository, path, repo_type="dataset", revision=revision)
    # Streaming prevents a server ignoring Range from returning the whole file.
    with httpx.stream(
        "GET", url, headers={"Range": "bytes=-8"}, follow_redirects=True, timeout=60
    ) as response:
        if response.status_code != 206:
            raise ValueError(f"Range reads unavailable for {file.file}")
        if response.headers.get("Content-Range") != (
            f"bytes {file.size - 8}-{file.size - 1}/{file.size}"
        ):
            raise ValueError(f"Unexpected range response for {file.file}")
        tail = response.read()
    if len(tail) != 8 or tail[4:] != b"PAR1":
        raise ValueError(f"Invalid Parquet footer for {file.file}")
    footer_bytes = int.from_bytes(tail[:4], "little") + 8
    if footer_bytes > file.size:
        raise ValueError(f"Invalid footer length for {file.file}")
    return footer_bytes


def prepare_comparison(
    dataset: Annotated[str, typer.Option(help="Dataset key in params.yaml.")],
    output: Annotated[Path, typer.Option(help="Prepared manifest directory.")],
    params: Annotated[Path, typer.Option()] = Path("params.yaml"),
) -> None:
    """Persist a file inventory and sampled group bounds using metadata only."""
    config = load_config(params)
    source = config.datasets[dataset].source
    specification = SOURCES[dataset]
    columns = specification.columns
    _, revision, _ = hub_path(source)
    files = source_files(source)
    # Stable ordering plus a separate source seed makes source additions independent.
    rng = random.Random(f"{config.seed}:{dataset}")  # noqa: S311
    draws: list[Draw] = []
    groups: dict[str, list[tuple[int, int, int, int]]] = {}
    footer_bytes = 0
    with stage_output(output) as staging, duckdb.connect() as con:
        con.execute("INSTALL httpfs; LOAD httpfs")
        for draw in range(config.draws):
            file = rng.choice(files)
            if file.file not in groups:
                footer_bytes += check_range(file)
                con.execute(
                    "CREATE OR REPLACE TEMP TABLE group_metadata AS "
                    "SELECT * FROM parquet_metadata($source)",
                    {"source": file.file},
                )
                con.execute(
                    "COPY group_metadata TO $target (FORMAT PARQUET)",
                    {"target": str(staging / f"metadata-{len(groups)}.parquet")},
                )
                rows = con.execute(
                    "SELECT row_group_id, max(row_group_num_rows), "
                    "coalesce(sum(total_compressed_size) FILTER (WHERE "
                    "trim(split_part(path_in_schema, ',', 1)) IN "
                    "(SELECT unnest($columns))), 0) "
                    "FROM group_metadata GROUP BY row_group_id ORDER BY row_group_id",
                    {"columns": list(columns)},
                ).fetchall()
                start = 0
                groups[file.file] = []
                for group_id, count, size in rows:
                    stop = start + int(count)
                    groups[file.file].append((int(group_id), start, stop, int(size)))
                    start = stop
                if not groups[file.file]:
                    raise ValueError(f"No row groups in {file.file}")
            choices = groups[file.file]
            group_id, start, stop, size = rng.choice(choices)
            draws.append(
                Draw(
                    draw=draw,
                    file=file.file,
                    row_group=group_id,
                    row_start=start,
                    row_stop=stop,
                    probability=1 / (len(files) * len(choices)),
                    file_size_bytes=file.size,
                    file_row_groups=len(choices),
                    projected_bytes=size,
                )
            )
        manifest = Manifest(
            dataset=dataset,
            source=source,
            revision=revision,
            seed=config.seed,
            file_count=len(files),
            listed_bytes=sum(file.size for file in files),
            english_definition=specification.english_definition,
            footer_bytes=footer_bytes,
            draws=draws,
        )
        (staging / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (staging / "files.json").write_text(
            json.dumps([file.model_dump() for file in files], indent=2) + "\n",
            encoding="utf-8",
        )
    unique = {(draw.file, draw.row_group): draw for draw in draws}
    typer.echo(
        f"{dataset}: {len(unique)} unique groups, "
        f"{sum(draw.row_stop - draw.row_start for draw in unique.values()):,} rows; "
        f"projected chunks {sum(draw.projected_bytes for draw in unique.values()):,} "
        f"bytes; footers {footer_bytes:,} bytes. Article data not acquired."
    )


def sample_comparison(
    dataset: Annotated[str, typer.Option(help="Dataset key in params.yaml.")],
    manifest: Annotated[Path, typer.Option(help="Prepared manifest JSON.")],
    output: Annotated[Path, typer.Option(help="Filtered sample directory.")],
    params: Annotated[Path, typer.Option()] = Path("params.yaml"),
) -> None:
    """Acquire the prepared groups and retain English publisher-matched records."""
    config = load_config(params)
    selection = Manifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    if (
        selection.dataset != dataset
        or selection.source != config.datasets[dataset].source
    ):
        raise ValueError("Manifest does not describe the configured dataset snapshot")
    if selection.seed != config.seed or len(selection.draws) != config.draws:
        raise ValueError("Sampling parameters changed; prepare a new manifest")
    counts: list[DrawCounts] = []
    cached: dict[tuple[str, int], dict[str, int]] = {}
    started = perf_counter()
    with stage_output(output) as staging, duckdb.connect() as con:
        con.execute("INSTALL httpfs; LOAD httpfs")
        for draw in selection.draws:
            key = (draw.file, draw.row_group)
            if key not in cached:
                check_range(
                    FileRecord(file=draw.file, size=draw.file_size_bytes, identity="")
                )
                cached[key] = extract_group(
                    con,
                    dataset,
                    draw.file,
                    draw.row_start,
                    draw.row_stop,
                    config.domains,
                    staging / f"group-{draw.draw}.parquet",
                )
                if cached[key]["input_rows"] != draw.row_stop - draw.row_start:
                    raise ValueError(
                        "Acquired row count differs from the prepared group"
                    )
            counts.append(DrawCounts(draw=draw.draw, **cached[key]))
        report = SampleCounts(
            dataset=dataset,
            draws=counts,
            elapsed_seconds=perf_counter() - started,
            output_bytes=sum(path.stat().st_size for path in staging.glob("*.parquet")),
        )
        report.ordered_counts(selection)
        (staging / "counts.json").write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    typer.echo(f"Wrote {dataset}: {len(cached)} unique groups -> {output}")
