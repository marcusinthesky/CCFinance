"""Adopt verified company candidates and preserve a compact article selection.

The selection is provisional lexical evidence, not adjudicated company relevance.
Article bodies remain in the immutable raw snapshot; source coordinates join each
index record back to its complete text without duplicating the corpus on disk.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import duckdb
import typer
from pydantic import BaseModel

VERSION = "article-labels-cpu-1"


class SourceFile(BaseModel):
    """One source file fingerprint from the completed candidate run."""

    index: int
    relative_path: str
    sha256: str
    bytes: int
    rows: int


class LegacyConfig(BaseModel):
    """Reference paths frozen by the original company matcher."""

    membership: Path
    registry: Path
    gh: Path


class LegacyManifest(BaseModel):
    """Required provenance from a completed, independently recorded run."""

    config: LegacyConfig
    contract_sha256: str
    source_population_rows: int
    source_files: list[SourceFile]
    registry_sha256: dict[str, str]


class Chunk(BaseModel):
    """A completed candidate chunk with its physical checksum."""

    file: str
    rows: int
    sha256: str


class Checkpoint(BaseModel):
    """The source-level commit marker produced by the legacy runner."""

    source_index: int
    source_sha256: str
    contract_sha256: str
    selection: dict[str, int]
    rows: int
    chunks: list[Chunk]


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _checkpoint(legacy: Path, source: SourceFile, contract: str) -> Checkpoint:
    directory = legacy / "shards" / f"{source.index:05d}"
    result = Checkpoint.model_validate_json((directory / "completed.json").read_bytes())
    if (
        result.source_index != source.index
        or result.source_sha256 != source.sha256
        or result.contract_sha256 != contract
        or result.selection != {"first": 0, "last": source.rows}
        or result.rows != source.rows
        or sum(chunk.rows for chunk in result.chunks) != source.rows
    ):
        raise ValueError(f"Candidate checkpoint differs from its source: {directory}")
    for chunk in result.chunks:
        if Path(chunk.file).name != chunk.file:
            raise ValueError("Candidate chunk paths must be local filenames")
        if _sha256(directory / chunk.file) != chunk.sha256:
            raise ValueError(
                f"Candidate chunk checksum differs: {directory / chunk.file}"
            )
    return result


def adopt_company_candidates(source: Path, legacy: Path, output: Path) -> None:
    """Copy a verified candidate snapshot without linking external file inodes.

    This local adoption is separate from processing. The snapshot includes all
    source checkpoints and company references, while excluding pilot predictions.
    """
    if output.exists():
        raise FileExistsError(f"Output exists: {output}")
    manifest = LegacyManifest.model_validate_json(
        (legacy / "manifest.json").read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / "snapshot"
        staging.mkdir()
        for name in ("manifest.json", "summary.json"):
            shutil.copyfile(legacy / name, staging / name)
        for record in manifest.source_files:
            path = source / record.relative_path
            if path.stat().st_size != record.bytes or _sha256(path) != record.sha256:
                raise ValueError(
                    f"Source checksum differs from candidate manifest: {path}"
                )
            checkpoint = _checkpoint(legacy, record, manifest.contract_sha256)
            relative = Path("shards") / f"{record.index:05d}"
            (staging / relative).mkdir(parents=True)
            for name in (
                "completed.json",
                *(chunk.file for chunk in checkpoint.chunks),
            ):
                shutil.copyfile(legacy / relative / name, staging / relative / name)
        references = staging / "references"
        references.mkdir()
        for key in ("membership", "registry", "gh"):
            reference = getattr(manifest.config, key)
            if not isinstance(reference, Path):
                raise TypeError("Company reference paths must be filesystem paths")
            if _sha256(reference) != manifest.registry_sha256[key]:
                raise ValueError(f"Company reference checksum differs: {reference}")
            shutil.copyfile(reference, references / f"{key}.csv")
        _json(
            staging / "adoption.json",
            {
                "source": str(source.resolve()),
                "legacy": str(legacy.resolve()),
                "contract_sha256": manifest.contract_sha256,
                "verification": (
                    "Source files, candidate chunks and references match SHA256."
                ),
                "copy_method": "Independent files; external inodes are not shared.",
            },
        )
        os.replace(staging, output)


_ARTICLES = """
CREATE TEMP TABLE articles AS
WITH joined AS (
    SELECT t.row_key AS article_id, a.id AS source_article_id,
        t.source_path, t.source_row, a.metadata.title AS title,
        a.metadata.url AS url, a.metadata.publish_date AS publish_date,
        t.year AS publish_year, t.top1000_coverage,
        sha256(a.text) AS text_sha256, length(a.text) AS text_chars,
        a.text IS NOT NULL AND length(trim(a.text)) > 0 AS usable_text,
        lower(rtrim(trim(coalesce(nullif(trim(a.metadata.url_hostname), ''),
            regexp_extract(a.metadata.url, '(?i)^https?://([^/:?#]+)', 1))), '.'))
            AS hostname,
        len(t.top1000_candidates) AS top1000_candidate_count,
        len(t.gh_candidates) AS gh_candidate_count,
        list_concat(t.top1000_candidates, t.gh_candidates) AS candidates
    FROM read_parquet($source, file_row_number=true, hive_partitioning=false) a
    JOIN read_parquet($tags, hive_partitioning=false) t
        ON a.file_row_number = t.source_row
), policy AS (
    SELECT *, top1000_candidate_count + gh_candidate_count AS candidate_count,
        coalesce('sha256:' || text_sha256, 'source:' || article_id) AS document_id,
        EXISTS (
            SELECT 1 FROM read_csv($domains, header=true) d
            WHERE hostname = lower(rtrim(trim(d.domain), '.'))
               OR ends_with(hostname, '.' || lower(rtrim(trim(d.domain), '.')))
        ) AS publisher_allowed
    FROM joined
)
SELECT * EXCLUDE (usable_text, publisher_allowed),
    publisher_allowed AND usable_text AND candidate_count > 0 AS retained,
    CASE WHEN NOT publisher_allowed THEN 'publisher_not_allowed'
         WHEN text_chars IS NULL THEN 'missing_text'
         WHEN NOT usable_text THEN 'empty_text'
         WHEN candidate_count = 0 THEN 'no_company_candidate'
         ELSE NULL END AS exclusion_reason,
    list_filter([
        CASE WHEN NOT publisher_allowed THEN 'publisher_not_allowed' END,
        CASE WHEN text_chars IS NULL THEN 'missing_text'
             WHEN NOT usable_text THEN 'empty_text' END,
        CASE WHEN publish_year IS NULL THEN 'unknown_publication_year' END,
        CASE WHEN top1000_coverage != 'complete'
             THEN top1000_coverage || '_company_catalog' END
    ], flag -> flag IS NOT NULL) AS quality_flags
FROM policy
"""


def _write_source(
    con: duckdb.DuckDBPyConnection,
    source: Path,
    legacy: Path,
    record: SourceFile,
    checkpoint: Checkpoint,
    domains: Path,
    destination: Path,
    contract: str,
) -> None:
    tags = [
        str(legacy / "shards" / f"{record.index:05d}" / c.file)
        for c in checkpoint.chunks
    ]
    bounds = con.execute(
        "SELECT count(*), count(DISTINCT source_row), "
        "min(source_row), max(source_row), "
        "count(*) FILTER (WHERE source_path != $relative OR row_key IS NULL) "
        "FROM read_parquet($tags)",
        {"tags": tags, "relative": record.relative_path},
    ).fetchone()
    if bounds != (record.rows, record.rows, 0, record.rows - 1, 0):
        raise ValueError(
            f"Candidate source coordinates do not reconcile: {record.relative_path}"
        )
    con.execute(
        _ARTICLES,
        {
            "source": str(source / record.relative_path),
            "tags": tags,
            "domains": str(domains),
        },
    )
    try:
        counts = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE retained) FROM articles"
        ).fetchone()
        if counts is None or counts[0] != record.rows:
            raise ValueError(
                f"Source row counts do not reconcile: {record.relative_path}"
            )
        with TemporaryDirectory(dir=destination.parent) as temporary:
            staging = Path(temporary) / "result"
            staging.mkdir()
            con.execute(
                "COPY (SELECT * EXCLUDE(retained, exclusion_reason), "
                "'retained' AS input_status "
                "FROM articles WHERE retained ORDER BY source_row) TO $target "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
                {"target": str(staging / "retained.parquet")},
            )
            con.execute(
                "COPY (SELECT * EXCLUDE(retained, candidates), "
                "'excluded' AS input_status "
                "FROM articles WHERE NOT retained ORDER BY source_row) TO $target "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
                {"target": str(staging / "excluded.parquet")},
            )
            con.execute(
                "COPY (SELECT article_id, source_path, source_row, "
                "document_id, text_sha256, "
                "publish_year, retained FROM articles ORDER BY source_row) TO $target "
                "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
                {"target": str(staging / "dedup-membership.parquet")},
            )
            _json(
                staging / "completed.json",
                {
                    "contract_sha256": contract,
                    "source_index": record.index,
                    "source_sha256": record.sha256,
                    "rows": record.rows,
                    "retained": counts[1],
                    "excluded": counts[0] - counts[1],
                    "outputs": {
                        name: _sha256(staging / name)
                        for name in (
                            "retained.parquet",
                            "excluded.parquet",
                            "dedup-membership.parquet",
                        )
                    },
                },
            )
            os.replace(staging, destination)
    finally:
        con.execute("DROP TABLE articles")


def prepare_article_labels(
    source: Annotated[Path, typer.Option(help="Verified raw Fine News snapshot.")],
    legacy: Annotated[Path, typer.Option(help="Adopted complete candidate snapshot.")],
    output: Annotated[Path, typer.Option(help="Compact CPU experiment artifacts.")],
    domains: Annotated[Path, typer.Option(help="Historical publisher-domain CSV.")],
    resume: Annotated[
        bool, typer.Option(help="Verify and reuse completed source outputs.")
    ] = True,
) -> None:
    """Select publisher articles with nonempty text and any company evidence.

    All original company candidates remain provisional. Unknown publication years
    and incomplete catalogs are flagged. No-hit and other excluded records remain
    in a separate index; article bodies stay in the source snapshot.
    """
    source, legacy, output = source.resolve(), legacy.resolve(), output.resolve()
    started = time.monotonic()
    manifest = LegacyManifest.model_validate_json(
        (legacy / "manifest.json").read_bytes()
    )
    references = {
        key: {"path": str(legacy / "references" / f"{key}.csv"), "sha256": digest}
        for key, digest in manifest.registry_sha256.items()
    }
    for key, reference in references.items():
        if _sha256(Path(reference["path"])) != manifest.registry_sha256[key]:
            raise ValueError(f"Adopted company reference differs: {key}")
    contract_data = {
        "version": VERSION,
        "source_root": str(source),
        "legacy_root": str(legacy),
        "legacy_manifest_sha256": _sha256(legacy / "manifest.json"),
        "legacy_contract_sha256": manifest.contract_sha256,
        "company_references": references,
        "domains": {"path": str(domains.resolve()), "sha256": _sha256(domains)},
        "implementation_sha256": _sha256(Path(__file__)),
        "source_files": [record.model_dump() for record in manifest.source_files],
        "deduplication": "Exact original text SHA256; source rows are retained.",
        "selection": (
            "Historical publishers, nonempty text, any top1000 or GH candidate."
        ),
    }
    contract = hashlib.sha256(
        json.dumps(contract_data, sort_keys=True).encode()
    ).hexdigest()
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if (
            not resume
            or manifest_path.read_text(encoding="utf-8")
            != json.dumps({**contract_data, "contract_sha256": contract}, indent=2)
            + "\n"
        ):
            raise ValueError("CPU output differs from the frozen experiment contract")
    else:
        if output.exists() and any(output.iterdir()):
            raise ValueError("CPU output has no manifest; use a fresh directory")
        output.mkdir(parents=True, exist_ok=True)
        _json(manifest_path, {**contract_data, "contract_sha256": contract})
    shards = output / "shards"
    shards.mkdir(exist_ok=True)
    retained, excluded = 0, 0
    with duckdb.connect(config={"threads": 4, "memory_limit": "2GB"}) as con:
        con.execute("SET enable_progress_bar=false")
        for record in manifest.source_files:
            path = source / record.relative_path
            if path.stat().st_size != record.bytes or _sha256(path) != record.sha256:
                raise ValueError(
                    f"Raw source differs from its verified snapshot: {path}"
                )
            checkpoint = _checkpoint(legacy, record, manifest.contract_sha256)
            destination = shards / f"{record.index:05d}"
            if destination.exists():
                report = json.loads((destination / "completed.json").read_text())
                if report["contract_sha256"] != contract or any(
                    _sha256(destination / name) != digest
                    for name, digest in report["outputs"].items()
                ):
                    raise ValueError(f"Completed CPU output differs: {destination}")
            else:
                _write_source(
                    con,
                    source,
                    legacy,
                    record,
                    checkpoint,
                    domains,
                    destination,
                    contract,
                )
                report = json.loads((destination / "completed.json").read_text())
            retained += int(report["retained"])
            excluded += int(report["excluded"])
            typer.echo(
                f"CPU {record.index + 1}/{len(manifest.source_files)}: "
                f"{retained:,} retained"
            )
        if retained + excluded != manifest.source_population_rows:
            raise ValueError(
                "CPU outputs do not reconcile with the full source population"
            )
        con.execute(
            "COPY (SELECT * FROM read_parquet($parts) "
            "ORDER BY source_path, source_row) "
            "TO $target (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
            {
                "parts": str(shards / "*/dedup-membership.parquet"),
                "target": str(output / "dedup-membership.parquet.tmp"),
            },
        )
        os.replace(
            output / "dedup-membership.parquet.tmp", output / "dedup-membership.parquet"
        )
    _json(
        output / "summary.json",
        {
            "status": "complete",
            "source_rows": retained + excluded,
            "retained_rows": retained,
            "excluded_rows": excluded,
            "source_files": len(manifest.source_files),
            "elapsed_seconds": time.monotonic() - started,
            "contract_sha256": contract,
            "semantics": (
                "Provisional company candidates; no substantive relevance claim."
            ),
        },
    )
