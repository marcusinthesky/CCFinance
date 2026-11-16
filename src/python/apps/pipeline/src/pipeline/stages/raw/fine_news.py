"""Reproduce the historical Fine News publisher filter."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import duckdb
import typer
from pydantic import BaseModel, ConfigDict

QUERY = """
    COPY (
        WITH articles AS (
            SELECT text, id, metadata, lower(rtrim(trim(coalesce(
                nullif(trim(metadata.url_hostname), ''),
                regexp_extract(metadata.url, '(?i)^https?://([^/:?#]+)', 1)
            )), '.')) AS hostname
            FROM read_parquet($source)
        )
        SELECT text, id, metadata FROM articles
        WHERE EXISTS (
            SELECT 1 FROM read_csv($domains, header=true) AS d
            WHERE hostname = lower(rtrim(trim(d.domain), '.'))
               OR ends_with(hostname, '.' || lower(rtrim(trim(d.domain), '.')))
        )
    ) TO $target (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 9,
                 ROW_GROUP_SIZE 16384)
"""


class FineNewsConfig(BaseModel):
    """Versioned inputs and output for the Fine News selection."""

    model_config = ConfigDict(extra="forbid")

    source: str
    domains: Path
    output: Path


def filter_fine_news(
    config: Annotated[
        Path, typer.Option(help="Historical acquisition configuration.")
    ] = Path("data/inputs/fine-news/acquisition.json"),
) -> None:
    """Select English publisher shards from a pinned Fine News revision."""
    settings = FineNewsConfig.model_validate_json(config.read_text(encoding="utf-8"))
    target = settings.output / "articles.parquet"
    if target.exists():
        raise FileExistsError(f"Output exists: {target}")
    settings.output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        if settings.source.startswith("hf://"):
            con.execute("INSTALL httpfs; LOAD httpfs")
        with TemporaryDirectory(dir=settings.output) as staging:
            temporary = Path(staging) / "articles.parquet"
            con.execute(
                QUERY,
                {
                    "source": settings.source,
                    "domains": str(settings.domains),
                    "target": str(temporary),
                },
            )
            os.link(temporary, target)
    typer.echo(f"Wrote: {settings.source} -> {target}")
