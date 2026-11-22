"""Build cleaned, deduplicated and enriched article and company tables."""

import typer

from pipeline.stages.processed.articles import prepare_articles
from pipeline.stages.processed.body_vectors import verify_body_vectors
from pipeline.stages.processed.company_links import link_companies
from pipeline.stages.processed.experiments.article_metadata import sample_articles
from pipeline.stages.processed.experiments.baker_emv.market import (
    prepare_baker_emv_market,
)
from pipeline.stages.processed.experiments.baker_emv.news import (
    measure_baker_emv,
)
from pipeline.stages.processed.experiments.company_links import (
    adjudicate_links,
)
from pipeline.stages.processed.experiments.entity_focus import judge_entity_focus
from pipeline.stages.processed.experiments.kazinnik_banks.matched_weeks import (
    prepare_kazinnik_matched_weeks,
)
from pipeline.stages.processed.experiments.kazinnik_banks.mentions import (
    prepare_kazinnik_banks,
)
from pipeline.stages.processed.experiments.lopez_lira_tang.events import (
    prepare_lopez_events,
)
from pipeline.stages.processed.experiments.lopez_lira_tang.recovered import (
    prepare_lopez_recovered,
)
from pipeline.stages.processed.experiments.lopez_lira_tang.sample import (
    prepare_lopez_sample,
)
from pipeline.stages.processed.experiments.lopez_lira_tang.titles import (
    project_lopez_titles,
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

app.command("measure-baker-emv")(measure_baker_emv)
app.command("prepare-baker-emv-market")(prepare_baker_emv_market)
app.command("prepare-kazinnik-banks")(prepare_kazinnik_banks)
app.command("prepare-kazinnik-matched-weeks")(prepare_kazinnik_matched_weeks)
app.command("prepare-lopez-events")(prepare_lopez_events)
app.command("prepare-lopez-recovered")(prepare_lopez_recovered)
app.command("prepare-lopez-sample")(prepare_lopez_sample)
app.command("project-lopez-titles")(project_lopez_titles)


@app.callback()
def main() -> None:
    """Build cleaned, deduplicated and enriched article and company tables."""


app.command("prepare-articles")(prepare_articles)
app.command("verify-body-vectors")(verify_body_vectors)
app.command("prepare-issuers")(prepare_issuers)
app.command("prepare-public-float")(prepare_public_float)
app.command("link-companies")(link_companies)
app.command("sample-articles")(sample_articles)
app.command("sample-links")(sample_links)
app.command("adjudicate-links")(adjudicate_links)
app.command("sample-metadata-pilot")(sample_metadata_pilot)
app.command("judge-metadata")(judge_metadata)
app.command("sample-metadata-confirmation")(sample_metadata_confirmation)

app.command("judge-entity-focus")(judge_entity_focus)
