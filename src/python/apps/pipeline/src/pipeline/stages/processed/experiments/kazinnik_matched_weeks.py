"""Build the matched earnings-week bridge over the fixed 2020 bank roster."""

import csv
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from typing import Annotated

import typer

from pipeline.stages.processed.experiments.kazinnik_banks import prepare_kazinnik_banks


def prepare_kazinnik_matched_weeks(
    articles: Annotated[Path, typer.Option(help="Canonical article catalog.")],
    links: Annotated[Path, typer.Option(help="Article-level company links directory.")],
    source: Annotated[
        Path, typer.Option(help="Raw Fine News shards by capture month.")
    ],
    issuers: Annotated[Path, typer.Option(help="Prepared issuer catalog.")],
    inputs: Annotated[
        Path, typer.Option(help="Bank roster and matched weeks protocol.")
    ],
    output: Annotated[Path, typer.Option(help="Output directory.")],
) -> None:
    """Reuse the bank join with the roster held fixed through April 2021."""
    with TemporaryDirectory() as directory:
        protocol = Path(directory)
        copyfile(inputs / "roster.csv", protocol / "roster.csv")
        copyfile(inputs / "matched-weeks.csv", protocol / "windows.csv")
        with (
            (inputs / "crosswalk.csv").open(encoding="utf-8", newline="") as source_csv,
            (protocol / "crosswalk.csv").open(
                "w", encoding="utf-8", newline=""
            ) as dest,
        ):
            reader = csv.DictReader(source_csv)
            writer = csv.DictWriter(dest, reader.fieldnames or ())
            writer.writeheader()
            for row in reader:
                if row["valid_through"] == "2020-04-30":
                    row["valid_through"] = "2021-04-30"
                writer.writerow(row)
        prepare_kazinnik_banks(articles, links, source, issuers, protocol, output)
