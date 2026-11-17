"""Draw a reproducible article sample for the metadata extraction benchmark."""

from pathlib import Path
from typing import Annotated

import duckdb
import typer


def sample_articles(
    source: Annotated[Path, typer.Option(help="Directory of raw article Parquet.")],
    diagnostics: Annotated[
        Path, typer.Option(help="Authored diagnostic articles as JSON lines.")
    ],
    output: Annotated[Path, typer.Option(help="New sample directory.")],
    size: Annotated[int, typer.Option(min=1)] = 10_000,
    seed: Annotated[int, typer.Option()] = 42,
) -> None:
    """Rank articles by SHA-256(seed:id), keep the first rows and add diagnostics.

    Hash priority gives a simple random sample without replacement that does not
    depend on file order. Diagnostic identifiers start with ``diagnostic:``.
    """
    output.mkdir(parents=True, exist_ok=False)
    with duckdb.connect() as con:
        con.execute(
            """COPY (
                (SELECT id, text FROM read_parquet($source)
                 ORDER BY sha256($seed || ':' || id) LIMIT $size)
                UNION ALL (SELECT id, text FROM read_json($diagnostics))
            ) TO $target (FORMAT parquet)""",
            {
                "source": str(source / "**" / "*.parquet"),
                "diagnostics": str(diagnostics),
                "seed": str(seed),
                "size": size,
                "target": str(output / "articles.parquet"),
            },
        )
    typer.echo(f"Sampled {size} articles: {source} -> {output}")
