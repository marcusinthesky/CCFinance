"""Extract publisher records from native pre-training dataset layouts."""

from dataclasses import dataclass
from pathlib import Path

import duckdb


def _hostname(host: str | None, url: str) -> str:
    return f"""lower(rtrim(trim(coalesce(
        nullif(trim({host or "NULL"}), ''),
        regexp_extract({url}, '(?i)^https?://([^/:?#]+)', 1)
    )), '.'))"""


PUBLISHER_MATCH = """
    EXISTS (
        SELECT 1 FROM read_csv($domains, header=true) AS d
        WHERE hostname = lower(rtrim(trim(d.domain), '.'))
           OR ends_with(hostname, '.' || lower(rtrim(trim(d.domain), '.')))
    )
"""


@dataclass(frozen=True)
class SourceSpec:
    """Declare native field mappings and derive the columns actually read.

    A metadata column is preserved as-is; a tuple of native fields is packed
    into a metadata struct. The optional language pair names its native column
    and English label. Expressions are authored here, never taken from config.
    """

    text: str
    identifier: str | None
    metadata: str | tuple[str, ...]
    url: str
    hostname: str | None
    english: tuple[str, str] | None
    english_definition: str

    @property
    def columns(self) -> tuple[str, ...]:
        """Return unique native roots needed for payload and footer estimates."""
        metadata = (self.metadata,) if isinstance(self.metadata, str) else self.metadata
        fields = [self.text]
        if self.identifier is not None and self.identifier not in metadata:
            fields.append(self.identifier)
        fields.extend(metadata)
        fields.append(self.url)
        if self.hostname is not None:
            fields.append(self.hostname)
        if self.english is not None:
            fields.append(self.english[0])
        return tuple(dict.fromkeys(field.split(".", 1)[0] for field in fields))

    @property
    def projection(self) -> str:
        """Project native fields into the shared article and filter columns."""
        metadata = (
            self.metadata
            if isinstance(self.metadata, str)
            else f"struct_pack({', '.join(self.metadata)})"
        )
        english = (
            "true"
            if self.english is None
            else f"{self.english[0]} = '{self.english[1]}'"
        )
        return (
            f"{self.text} AS text, {self.identifier or 'NULL::VARCHAR'} AS id, "
            f"{metadata} AS metadata, {english} AS _english, "
            f"{_hostname(self.hostname, self.url)} AS hostname"
        )


SOURCES: dict[str, SourceSpec] = {
    "fine_news": SourceSpec(
        text="text",
        identifier="id",
        metadata="metadata",
        url="metadata.url",
        hostname="metadata.url_hostname",
        english=None,
        english_definition="Files in the source's eng_Latn directories.",
    ),
    "infini_news": SourceSpec(
        text="text",
        identifier="warc_record_id",
        metadata=(
            "url",
            "url_hostname",
            "warc_record_id",
            "warc_filename",
            "warc_date",
            "publish_date",
            "title",
            "author",
            "sitename",
            "categories",
            "tags",
            "description",
            "language",
            "language_score",
        ),
        url="url",
        hostname="url_hostname",
        english=("language", "eng_Latn"),
        english_definition="Records whose native language label equals eng_Latn.",
    ),
    "refinedweb": SourceSpec(
        text="content",
        identifier=None,
        metadata=("url", "timestamp", "dump", "segment"),
        url="url",
        hostname=None,
        english=None,
        english_definition="The source release declares its records to be English.",
    ),
    "fineweb_hq": SourceSpec(
        text="text",
        identifier="id",
        metadata=(
            "date",
            "dump",
            "file_path",
            "language",
            "language_score",
            "token_count",
            "url",
            "quality_score",
        ),
        url="url",
        hostname=None,
        english=("language", "en"),
        english_definition="Records whose native language label equals en.",
    ),
}


def write_parquet(
    con: duckdb.DuckDBPyConnection,
    query: str,
    parameters: dict[str, object],
    target: Path,
) -> None:
    """Write a fresh Parquet file inside the caller's publication boundary."""
    if target.exists():
        raise FileExistsError(f"Output exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({query}) TO $target "
        "(FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 9, "
        "ROW_GROUP_SIZE 16384)",
        {**parameters, "target": str(target)},
    )


def extract_group(
    con: duckdb.DuckDBPyConnection,
    dataset: str,
    source: str,
    row_start: int,
    row_stop: int,
    domains: Path,
    target: Path,
) -> dict[str, int]:
    """Read one row interval once and retain its English publisher records.

    Bounds are zero-based and stop-exclusive. Restricting the virtual Parquet
    row number at the scan enables remote row-group pruning. The temporary table
    preserves the selected input for counts and copying without a second read.
    The caller owns the staging directory and publishes the completed stage.
    """
    if row_start < 0 or row_stop <= row_start:
        raise ValueError("A nonempty, nonnegative row interval is required.")
    if target.exists():
        raise FileExistsError(f"Output exists: {target}")
    con.execute(
        f"""CREATE TEMP TABLE comparison_group AS
        SELECT {SOURCES[dataset].projection},
            $source AS source_file, file_row_number AS source_row
        FROM read_parquet($source, file_row_number=true, hive_partitioning=false)
        WHERE file_row_number >= $row_start AND file_row_number < $row_stop
        """,  # noqa: S608 - projection comes from the fixed source registry.
        {"source": source, "row_start": row_start, "row_stop": row_stop},
    )
    try:
        counts = con.execute(
            f"""SELECT count(*), count(*) FILTER (WHERE _english),
                count(*) FILTER (WHERE _english AND {PUBLISHER_MATCH})
                FROM comparison_group""",  # noqa: S608 - authored predicate.
            {"domains": str(domains)},
        ).fetchone()
        if counts is None or counts[0] != row_stop - row_start:
            raise ValueError("The selected row interval differs from its manifest.")
        write_parquet(
            con,
            f"""SELECT * EXCLUDE (_english, hostname) FROM comparison_group
                WHERE _english AND {PUBLISHER_MATCH}""",  # noqa: S608
            {"domains": str(domains)},
            target,
        )
        return dict(
            zip(("input_rows", "english_rows", "matched_rows"), counts, strict=True)
        )
    finally:
        con.execute("DROP TABLE comparison_group")
