"""Preserve versioned source snapshots and provenance."""

import typer

from pipeline.stages.raw.experiments.source_comparison import (
    prepare_comparison,
    sample_comparison,
)
from pipeline.stages.raw.fine_news import filter_fine_news
from pipeline.stages.raw.issuers import snapshot_issuers

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Preserve versioned source snapshots and provenance."""


app.command("filter-fine-news")(filter_fine_news)
app.command("prepare-comparison")(prepare_comparison)
app.command("sample-comparison")(sample_comparison)
app.command("snapshot-issuers")(snapshot_issuers)
