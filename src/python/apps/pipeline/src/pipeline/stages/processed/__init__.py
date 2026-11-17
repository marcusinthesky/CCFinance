"""Build cleaned, deduplicated and enriched article and company tables."""

import typer

from pipeline.stages.processed.experiments.article_candidates import (
    correct_article_candidates,
)
from pipeline.stages.processed.experiments.article_labels import (
    adopt_company_candidates,
    prepare_article_labels,
)
from pipeline.stages.processed.experiments.article_scoring import (
    benchmark_article_labels,
    score_articles,
)

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Build cleaned, deduplicated and enriched article and company tables."""


app.command("adopt-company-candidates")(adopt_company_candidates)
app.command("prepare-article-labels")(prepare_article_labels)
app.command("correct-article-candidates")(correct_article_candidates)
app.command("benchmark-article-labels")(benchmark_article_labels)
app.command("score-articles")(score_articles)
