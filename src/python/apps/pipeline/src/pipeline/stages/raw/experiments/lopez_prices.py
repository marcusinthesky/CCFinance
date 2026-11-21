"""Preserve Yahoo chart responses for the overnight body-vector study."""

import csv
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import typer

ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/"
QUERY = "?period1=1609286400&period2=1717286400&interval=1d&events=div%2Csplits"


def snapshot_lopez_prices(
    symbols: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    *,
    index_existing: bool = False,
) -> None:
    """Snapshot a fixed list of symbols with failures and retrieval instants."""
    responses = output / "prices"
    responses.mkdir(parents=True, exist_ok=True)
    with (
        symbols.open() as requests,
        (output / "requests.csv").open("w", newline="") as ledger,
    ):
        writer = csv.writer(ledger)
        writer.writerow(("symbol", "url", "retrieved_utc", "status", "sha256"))
        for row in csv.DictReader(requests):
            symbol = row["symbol"]
            if re.fullmatch(r"[A-Za-z0-9.-]+", symbol) is None or symbol in {".", ".."}:
                msg = f"Invalid Yahoo symbol {symbol!r}"
                raise ValueError(msg)
            url = ENDPOINT + symbol + QUERY
            destination = responses / f"{symbol}.json"
            if index_existing:
                if destination.exists():
                    captured = datetime.fromtimestamp(destination.stat().st_mtime, UTC)
                    body = destination.read_bytes()
                    status = "archived_response"
                else:
                    writer.writerow((symbol, url, "", "no_archived_response", ""))
                    continue
            else:
                captured = datetime.now(UTC)
                try:
                    # The provider and URL scheme are fixed in ENDPOINT.
                    request = Request(  # noqa: S310
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with urlopen(request, timeout=30) as response:  # noqa: S310
                        body = response.read()
                        status = str(response.status)
                except HTTPError as error:
                    body = error.read()
                    status = str(error.code)
                except (URLError, TimeoutError) as error:
                    destination.unlink(missing_ok=True)
                    writer.writerow((symbol, url, captured.isoformat(), str(error), ""))
                    continue
                temporary = destination.with_suffix(".tmp")
                temporary.write_bytes(body)
                temporary.replace(destination)
            writer.writerow(
                (
                    symbol,
                    url,
                    captured.isoformat(),
                    status,
                    hashlib.sha256(body).hexdigest(),
                )
            )
