"""Build cleaned, deduplicated and enriched article and company tables."""

import typer

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Build cleaned, deduplicated and enriched article and company tables."""
