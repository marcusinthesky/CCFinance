"""Curate coverage panels, study cohorts and release datasets."""

import typer

from pipeline.stages.research.coverage import build_coverage_panel
from pipeline.stages.research.experiments.article_metadata import (
    report_article_metadata,
)
from pipeline.stages.research.experiments.baker_emv import (
    build_baker_emv_panel,
    report_baker_emv,
)
from pipeline.stages.research.experiments.baker_tracking import compare_baker_tracking
from pipeline.stages.research.experiments.company_focus import report_company_focus
from pipeline.stages.research.experiments.company_links import report_company_links
from pipeline.stages.research.experiments.coverage import report_coverage
from pipeline.stages.research.experiments.entity_focus import score_entity_focus
from pipeline.stages.research.experiments.kazinnik_banks import report_kazinnik_banks
from pipeline.stages.research.experiments.kazinnik_matched_weeks import (
    report_kazinnik_matched_weeks,
)
from pipeline.stages.research.experiments.lopez_lira_tang import (
    fit_lopez_probes,
    report_lopez_portfolios,
    report_lopez_title_probes,
)
from pipeline.stages.research.experiments.metadata_validation import (
    report_metadata_validation,
)
from pipeline.stages.research.experiments.source_comparison import compare_sources

app = typer.Typer(no_args_is_help=True, help=__doc__)

app.command("build-baker-emv-panel")(build_baker_emv_panel)
app.command("report-baker-emv")(report_baker_emv)
app.command("compare-baker-tracking")(compare_baker_tracking)

app.command("report-kazinnik-banks")(report_kazinnik_banks)
app.command("report-kazinnik-matched-weeks")(report_kazinnik_matched_weeks)
app.command("fit-lopez-probes")(fit_lopez_probes)
app.command("report-lopez-portfolios")(report_lopez_portfolios)
app.command("report-lopez-title-probes")(report_lopez_title_probes)


@app.callback()
def main() -> None:
    """Curate coverage panels, study cohorts and release datasets."""


app.command("build-coverage-panel")(build_coverage_panel)
app.command("compare-sources")(compare_sources)
app.command("report-article-metadata")(report_article_metadata)
app.command("report-company-links")(report_company_links)
app.command("report-company-focus")(report_company_focus)
app.command("report-coverage")(report_coverage)
app.command("report-metadata-validation")(report_metadata_validation)

app.command("score-entity-focus")(score_entity_focus)
