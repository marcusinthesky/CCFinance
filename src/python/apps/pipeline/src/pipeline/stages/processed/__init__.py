"""Build cleaned, deduplicated and enriched article and company tables."""

import typer

from pipeline.stages.processed.articles import prepare_articles
from pipeline.stages.processed.company_links import link_companies
from pipeline.stages.processed.experiments.article_metadata import sample_articles
from pipeline.stages.processed.experiments.company_links import (
    adjudicate_links,
)
from pipeline.stages.processed.experiments.metadata_judges import judge_metadata
from pipeline.stages.processed.experiments.metadata_validation import (
    sample_metadata_confirmation,
    sample_metadata_pilot,
)
from pipeline.stages.processed.experiments.sample_links import sample_links
from pipeline.stages.processed.issuers import prepare_issuers
from pipeline.stages.processed.public_float import prepare_public_float

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Build cleaned, deduplicated and enriched article and company tables."""


app.command("prepare-articles")(prepare_articles)
app.command("prepare-issuers")(prepare_issuers)
app.command("prepare-public-float")(prepare_public_float)
app.command("link-companies")(link_companies)
app.command("sample-articles")(sample_articles)
app.command("sample-links")(sample_links)
app.command("adjudicate-links")(adjudicate_links)
app.command("sample-metadata-pilot")(sample_metadata_pilot)
app.command("judge-metadata")(judge_metadata)
app.command("sample-metadata-confirmation")(sample_metadata_confirmation)
