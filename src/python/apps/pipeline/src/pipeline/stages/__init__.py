"""Data processing stage commands, implemented alongside their stage modules."""

import typer

app = typer.Typer(no_args_is_help=True, help="Data processing stages.")


@app.command(name="list")
def list_stages() -> None:
    """Show implemented stages; the research pipeline follows in part 2."""
    typer.echo("No data processing stages registered yet (part 2).")
