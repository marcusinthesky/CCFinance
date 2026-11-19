"""Snapshot SEC public float, the issuer-size measure on annual report covers.

Filers report the market value of shares held by non-affiliates
(``dei:EntityPublicFloat``) as of the last business day of their second fiscal
quarter. SEC XBRL frames publish, for each calendar quarter, the latest filed
value for every filer whose measurement date falls in it. All four quarters of
each year are kept, so fiscal years ending in any month are covered. A frame
SEC has not published yet (404) is recorded as missing rather than failing.
"""

import json
from pathlib import Path
from typing import Annotated

import httpx
import typer

from pipeline.stages.raw.issuers import download, snapshot_client
from pipeline.stages.raw.staging import stage_output

FRAMES = "https://data.sec.gov/api/xbrl/frames/dei/EntityPublicFloat/USD/{period}.json"


def periods(first_year: int, last_year: int) -> list[str]:
    """Calendar-quarter instant frames, such as CY2019Q2I, for each year."""
    return [
        f"CY{year}Q{quarter}I"
        for year in range(first_year, last_year + 1)
        for quarter in range(1, 5)
    ]


def snapshot(client: httpx.Client, frames: list[str], output: Path) -> None:
    """Write each published public-float frame, with provenance."""
    with stage_output(output) as staging:
        (staging / "frames").mkdir()
        provenance: dict[str, object] = {}
        for period in frames:
            url = FRAMES.format(period=period)
            try:
                record = download(client, url, staging / "frames" / f"{period}.json")
            except httpx.HTTPStatusError as error:
                if error.response.status_code != httpx.codes.NOT_FOUND:
                    raise
                record = {"url": url, "status": "not published"}
            provenance[f"frames/{period}.json"] = record
        (staging / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n"
        )


def snapshot_public_float(
    user_agent: Annotated[
        str,
        typer.Option(
            envvar="SEC_USER_AGENT",
            help="Requester and contact, as SEC fair-access rules require.",
        ),
    ],
    first_year: Annotated[int, typer.Option(help="First calendar year.")] = 2015,
    last_year: Annotated[int, typer.Option(help="Last calendar year.")] = 2026,
    output: Annotated[Path, typer.Option(help="New snapshot directory.")] = Path(
        "data/raw/public-float"
    ),
) -> None:
    """Snapshot SEC public-float frames for every quarter of the given years."""
    with snapshot_client(user_agent, timeout=120) as client:
        snapshot(client, periods(first_year, last_year), output)
    typer.echo(f"Wrote: {output}")
