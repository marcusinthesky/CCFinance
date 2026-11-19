"""Snapshot public SEC and Wikidata issuer references with provenance."""

import csv
import hashlib
import json
import re
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer

from pipeline.stages.raw.experiments.source_comparison import stage_output

SEC_TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SUBMISSIONS = (
    "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
)
WIKIDATA = "https://query.wikidata.org/sparql"
QUERIES = ("tickers", "names", "parents", "owners")
RETRIES = 5


def pace_sec_request(request: httpx.Request) -> None:
    """Pace every SEC attempt, including redirects and retries."""
    if request.url.host == "sec.gov" or request.url.host.endswith(".sec.gov"):
        time.sleep(0.2)


def snapshot_client(user_agent: str, timeout: int) -> httpx.Client:
    """Validate the contact before beginning either network snapshot."""
    contact = user_agent.strip()
    if (
        not contact.isascii()
        or not contact.isprintable()
        or not re.fullmatch(r".+\s+[^\s@]+@[^\s@]+\.[^\s@]+", contact)
    ):
        raise typer.BadParameter("SEC_USER_AGENT requires a name and email.")
    return httpx.Client(
        headers={"User-Agent": contact},
        follow_redirects=True,
        event_hooks={"request": [pace_sec_request]},
        timeout=timeout,
    )


SUBMISSION_FIELDS = (
    "cik",
    "name",
    "entityType",
    "sic",
    "sicDescription",
    "tickers",
    "exchanges",
    "formerNames",
)


def download(
    client: httpx.Client,
    url: str,
    target: Path,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    """Stream one response to disk and describe what was retrieved.

    Rate limits (429) and outages (503) are retried after `Retry-After`, or a
    minute, which fits the Wikidata Query Service's strictest published limit.
    """
    digest = hashlib.sha256()
    for attempt in range(RETRIES + 1):
        with client.stream("GET", url, params=params, headers=headers) as response:
            if response.status_code in (429, 503) and attempt < RETRIES:
                retry = response.headers.get("retry-after", "")
                time.sleep(float(retry) if retry.isdigit() else 65)
                continue
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    digest.update(chunk)
                    handle.write(chunk)
            break
    return {
        "url": url,
        "retrieved": datetime.now(UTC).isoformat(timespec="seconds"),
        "last_modified": response.headers.get("last-modified"),
        "sha256": digest.hexdigest(),
        "bytes": target.stat().st_size,
    }


def listed_ciks(sec_tickers: Path, wikidata_tickers: Path) -> set[int]:
    """Return every CIK either source associates with an exchange listing."""
    ciks = {row[0] for row in json.loads(sec_tickers.read_text())["data"]}
    with wikidata_tickers.open(newline="", encoding="utf-8") as handle:
        ciks |= {
            int(row["cik"]) for row in csv.DictReader(handle) if row["cik"].isdigit()
        }
    return ciks


def subset_submissions(archive: Path, ciks: set[int], target: Path) -> int:
    """Keep issuer identity fields for the given CIKs, without filing lists."""
    written = 0
    with zipfile.ZipFile(archive) as bundle, target.open("w") as output:
        members = set(bundle.namelist())
        for cik in sorted(ciks):
            member = f"CIK{cik:010d}.json"
            if member not in members:
                continue
            record = json.loads(bundle.read(member))
            subset = {field: record.get(field) for field in SUBMISSION_FIELDS}
            output.write(json.dumps(subset, sort_keys=True) + "\n")
            written += 1
    return written


def snapshot(client: httpx.Client, queries: Path, output: Path) -> None:
    """Write SEC listings, submission identities and Wikidata query results."""
    with stage_output(output) as staging:
        (staging / "sec").mkdir()
        (staging / "wikidata").mkdir()
        provenance: dict[str, object] = {}
        for name in QUERIES:
            query = (queries / f"{name}.rq").read_text(encoding="utf-8")
            record = download(
                client,
                WIKIDATA,
                staging / "wikidata" / f"{name}.csv",
                params={"query": query},
                headers={"Accept": "text/csv"},
            )
            record["query_sha256"] = hashlib.sha256(query.encode()).hexdigest()
            provenance[f"wikidata/{name}.csv"] = record
        tickers = staging / "sec" / "company_tickers_exchange.json"
        provenance["sec/company_tickers_exchange.json"] = download(
            client, SEC_TICKERS, tickers
        )
        archive = staging / "submissions.zip"
        record = download(client, SEC_SUBMISSIONS, archive)
        ciks = listed_ciks(tickers, staging / "wikidata" / "tickers.csv")
        target = staging / "sec" / "submissions.jsonl"
        record["records"] = subset_submissions(archive, ciks, target)
        record["subset_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        provenance["sec/submissions.jsonl"] = record
        archive.unlink()
        (staging / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n"
        )


def snapshot_issuers(
    user_agent: Annotated[
        str,
        typer.Option(
            envvar="SEC_USER_AGENT",
            help="Requester and contact, as SEC fair-access rules require.",
        ),
    ],
    queries: Annotated[Path, typer.Option(help="Wikidata SPARQL queries.")] = Path(
        "data/inputs/issuers"
    ),
    output: Annotated[Path, typer.Option(help="New snapshot directory.")] = Path(
        "data/raw/issuers"
    ),
) -> None:
    """Snapshot SEC listings and identities, plus Wikidata tickers and names."""
    with snapshot_client(user_agent, timeout=300) as client:
        snapshot(client, queries, output)
    typer.echo(f"Wrote: {output}")
