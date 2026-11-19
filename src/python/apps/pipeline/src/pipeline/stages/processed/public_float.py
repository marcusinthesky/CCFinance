"""Tabulate SEC public float by filer and measurement date.

Each frame holds one value per filer; a filer's measurement date falls in one
calendar quarter, so rows are unique by CIK and date. Values are US dollars.
"""

import json
from pathlib import Path
from typing import Annotated

import duckdb
import typer


def prepare_public_float(
    source: Annotated[Path, typer.Option(help="Public-float snapshot.")] = Path(
        "data/raw/public-float"
    ),
    output: Annotated[Path, typer.Option(help="Output directory.")] = Path(
        "data/processed/public-float"
    ),
) -> None:
    """Write one row per filer and measurement date, with its source frame."""
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for frame in sorted((source / "frames").glob("*.json")):
        payload = json.loads(frame.read_text())
        rows.extend(
            (fact["cik"], fact["end"], fact["val"], fact["accn"], frame.stem)
            for fact in payload["data"]
        )
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE facts (cik BIGINT, measured DATE, value_usd DOUBLE, "
            "accession VARCHAR, frame VARCHAR)"
        )
        con.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?)", rows)
        latest = con.sql(
            "SELECT * FROM facts QUALIFY row_number() OVER ("
            "PARTITION BY cik, measured ORDER BY accession DESC) = 1 "
            "ORDER BY cik, measured"
        )
        latest.write_parquet(str(output / "public_float.parquet"), compression="zstd")
        count = latest.count("*").fetchall()[0][0]
    typer.echo(f"Wrote: {output} ({count} filer-dates)")
