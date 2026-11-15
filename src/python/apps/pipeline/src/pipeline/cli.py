"""Thin command line interface; stage logic belongs in pipeline.stages."""

import typer

from pipeline.stages import app as stages_app

app = typer.Typer(no_args_is_help=True, help="CCFinance reproducible data pipeline.")
app.add_typer(stages_app, name="stages")


@app.command()
def version() -> None:
    """Print the installed pipeline version."""
    from importlib.metadata import version as package_version

    typer.echo(package_version("ccfinance-pipeline"))
