"""Preserve versioned source snapshots and provenance."""

import typer

app = typer.Typer(no_args_is_help=True, help=__doc__)


@app.callback()
def main() -> None:
    """Preserve versioned source snapshots and provenance."""
