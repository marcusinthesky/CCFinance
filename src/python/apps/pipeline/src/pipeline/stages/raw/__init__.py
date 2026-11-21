"""Preserve versioned source snapshots and provenance."""

import typer

from pipeline.stages.raw.experiments.baker_emv import snapshot_baker_emv
from pipeline.stages.raw.experiments.lopez_prices import snapshot_lopez_prices
from pipeline.stages.raw.experiments.source_comparison import (
    prepare_comparison,
    sample_comparison,
)
from pipeline.stages.raw.fine_news import filter_fine_news
from pipeline.stages.raw.issuers import snapshot_issuers
from pipeline.stages.raw.public_float import snapshot_public_float

app = typer.Typer(no_args_is_help=True, help=__doc__)

app.command("snapshot-baker-emv")(snapshot_baker_emv)
app.command("snapshot-lopez-prices")(snapshot_lopez_prices)


@app.callback()
def main() -> None:
    """Preserve versioned source snapshots and provenance."""


app.command("filter-fine-news")(filter_fine_news)
app.command("prepare-comparison")(prepare_comparison)
app.command("sample-comparison")(sample_comparison)
app.command("snapshot-issuers")(snapshot_issuers)
app.command("snapshot-public-float")(snapshot_public_float)
