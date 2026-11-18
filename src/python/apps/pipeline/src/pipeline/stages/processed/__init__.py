"""Build cleaned, deduplicated and enriched article and company tables."""

import typer

from pipeline.stages.processed.company_links import link_companies
from pipeline.stages.processed.experiments.article_metadata import sample_articles
from pipeline.stages.processed.experiments.company_links import (
    adjudicate_links,
    sample_links,
)
from pipeline.stages.processed.issuers import prepare_issuers

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Build cleaned, deduplicated and enriched article and company tables."""


app.command("prepare-issuers")(prepare_issuers)
app.command("link-companies")(link_companies)
app.command("sample-articles")(sample_articles)
app.command("sample-links")(sample_links)
app.command("adjudicate-links")(adjudicate_links)
