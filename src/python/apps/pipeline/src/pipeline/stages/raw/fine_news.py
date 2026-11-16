"""Preserve the historical Fine News publisher acquisition command."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import duckdb
import typer
from pydantic import BaseModel, ConfigDict

from pipeline.stages.raw.publishers import PUBLISHER_MATCH, SOURCES, write_parquet


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
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as staging, duckdb.connect() as con:
        if settings.source.startswith("hf://"):
            con.execute("INSTALL httpfs; LOAD httpfs")
        temporary = Path(staging) / "articles.parquet"
        write_parquet(
            con,
            f"""WITH articles AS (
                SELECT {SOURCES["fine_news"].projection} FROM read_parquet($source)
            ) SELECT text, id, metadata FROM articles WHERE {PUBLISHER_MATCH}""",  # noqa: S608 - authored projection and predicate.
            {"source": settings.source, "domains": str(settings.domains)},
            temporary,
        )
        os.link(temporary, target)
    typer.echo(f"Wrote: {settings.source} -> {target}")
