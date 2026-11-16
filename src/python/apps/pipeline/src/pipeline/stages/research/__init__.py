"""Curate coverage panels, study cohorts and release datasets."""

import typer

from pipeline.stages.research.experiments.source_comparison import compare_sources

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Curate coverage panels, study cohorts and release datasets."""


app.command("compare-sources")(compare_sources)
