"""Snapshot the authors' replication archive and market closes."""

import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import typer

from pipeline.stages.raw.issuers import download
from pipeline.stages.raw.staging import stage_output

INPUTS = Path("data/inputs/baker-emv")
RAW = Path("data/raw/experiments/baker-emv")
ARCHIVE_URL = (
    "https://data.mendeley.com/public-files/datasets/rmhtcwnvrk/files/"
    "06f7a6d9-4cc9-471b-bfce-dfe7cbe8ceb9/file_downloaded"
)
ARCHIVE_SHA256 = "05032793137ed46f73a86fd7d7b3896fa1b02c1422b27d15a33e3965dce1e9a9"
FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def snapshot_baker_emv(
    window: Path = INPUTS / "window.json",
    output: Path = RAW,
) -> None:
    """Save the checksum-verified author archive and dated market sources."""
    bounds = json.loads(window.read_text())
    start = date.fromisoformat(bounds["start"]) - timedelta(days=14)
    # A calendar month is shorter than 32 days.
    end = (date.fromisoformat(bounds["end"]) + timedelta(days=32)).replace(day=1)
    end -= timedelta(days=1)
    market_url = f"{FRED_GRAPH}?id=VIXCLS,SP500&cosd={start}&coed={end}"
    with (
        stage_output(output) as staging,
        httpx.Client(timeout=180, follow_redirects=True) as client,
    ):
        archive = download(client, ARCHIVE_URL, staging / "replication.rar")
        if archive["sha256"] != ARCHIVE_SHA256:
            raise ValueError("Mendeley archive does not match its published SHA-256")
        market = download(client, market_url, staging / "market.csv")
        provenance = {"replication.rar": archive, "market.csv": market}
        (staging / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
    typer.echo(f"Wrote: {output}")
