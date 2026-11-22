"""Project captured titles for offline encoding."""

from pathlib import Path
from typing import Annotated

import duckdb
import typer


def project_lopez_titles(
    sample: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Project one captured title per fixed sample article for offline encoding."""
    with duckdb.connect() as con:
        titles = (
            con.read_parquet(str(sample / "sample.parquet"))
            .project("id, title AS text")
            .distinct()
        )
        if titles.filter("id IS NULL OR text IS NULL OR trim(text) = ''").shape[0]:
            msg = "The fixed sample contains a missing article ID or title"
            raise ValueError(msg)
        if titles.aggregate("count(*) <> count(DISTINCT id)").fetchone() == (True,):
            msg = "A fixed sample article has multiple captured titles"
            raise ValueError(msg)
        output.mkdir(parents=True, exist_ok=True)
        titles.order("id").write_parquet(str(output / "titles.parquet"))
