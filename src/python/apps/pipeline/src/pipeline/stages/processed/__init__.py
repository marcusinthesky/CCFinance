"""Build cleaned, deduplicated and enriched article and company tables."""

import typer

from pipeline.stages.processed.experiments.article_metadata import sample_articles
from pipeline.stages.processed.issuers import prepare_issuers

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Build cleaned, deduplicated and enriched article and company tables."""


app.command("prepare-issuers")(prepare_issuers)
app.command("sample-articles")(sample_articles)
