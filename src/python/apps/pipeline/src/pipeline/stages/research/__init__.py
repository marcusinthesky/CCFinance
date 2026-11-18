"""Curate coverage panels, study cohorts and release datasets."""

import typer

from pipeline.stages.research.experiments.article_metadata import (
    report_article_metadata,
)
from pipeline.stages.research.experiments.company_links import report_company_links
from pipeline.stages.research.experiments.source_comparison import compare_sources

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Curate coverage panels, study cohorts and release datasets."""


app.command("compare-sources")(compare_sources)
app.command("report-article-metadata")(report_article_metadata)
app.command("report-company-links")(report_company_links)
