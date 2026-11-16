"""Preserve versioned source snapshots and provenance."""

import typer

from pipeline.stages.raw.fine_news import filter_fine_news

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Preserve versioned source snapshots and provenance."""


app.command("filter-fine-news")(filter_fine_news)
