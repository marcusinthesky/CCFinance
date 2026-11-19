"""Exercise the issuer snapshot against an in-memory SEC and Wikidata."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import typer
from pipeline.stages.raw.issuers import (
    QUERIES,
    pace_sec_request,
    snapshot,
    snapshot_client,
)


def _archive(records: dict[int, dict[str, object]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for cik, record in records.items():
            bundle.writestr(f"CIK{cik:010d}.json", json.dumps(record))
    return buffer.getvalue()


@pytest.mark.integration
def test_snapshot_keeps_listed_identities_with_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: SEC lists Apple; Wikidata adds delisted Twitter after a rate limit.
    queries = tmp_path / "queries"
    queries.mkdir()
    for name in QUERIES:
        (queries / f"{name}.rq").write_text(f"SELECT {name}", encoding="utf-8")
    tickers = "item,cik,exchange,exchangeLabel,ticker,start,end\n"
    tickers += "Q1,0001418091,Q2,NYSE,TWTR,,\n"
    listing = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
    }
    records: dict[int, dict[str, object]] = {
        320193: {"name": "APPLE INC", "filings": {"recent": {"form": ["10-K"]}}},
        1418091: {"name": "TWITTER, INC."},
        7: {"name": "UNLISTED"},
    }
    archive = _archive(records)
    waits: list[float] = []
    monkeypatch.setattr("pipeline.stages.raw.issuers.time.sleep", waits.append)

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "query.wikidata.org" and not waits:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if request.url.host == "query.wikidata.org":
            query = request.url.params["query"]
            return httpx.Response(
                200, text=tickers if query == "SELECT tickers" else "item\n"
            )
        if request.url.path.endswith(".json"):
            return httpx.Response(200, json=listing)
        return httpx.Response(200, content=archive)

    output = tmp_path / "issuers"

    # Act: snapshot every source through the mocked transport.
    with httpx.Client(
        transport=httpx.MockTransport(respond),
        event_hooks={"request": [pace_sec_request]},
    ) as client:
        snapshot(client, queries, output)

    # Assert: identities are subset to listed CIKs, without filings or the archive.
    lines = (output / "sec/submissions.jsonl").read_text().splitlines()
    assert [json.loads(line)["name"] for line in lines] == [
        "APPLE INC",
        "TWITTER, INC.",
    ]
    assert all("filings" not in json.loads(line) for line in lines)
    assert not (output / "submissions.zip").exists()
    provenance = json.loads((output / "provenance.json").read_text())
    for path, record in provenance.items():
        data = (output / path).read_bytes()
        expected = record.get("subset_sha256", record["sha256"])
        assert hashlib.sha256(data).hexdigest() == expected
    assert provenance["sec/submissions.jsonl"]["records"] == 2
    assert waits == [7.0, 0.2, 0.2]
    with pytest.raises(FileExistsError):
        snapshot(httpx.Client(transport=httpx.MockTransport(respond)), queries, output)


@pytest.mark.unit
def test_missing_contact_fails_before_network_access() -> None:
    # Arrange: the shell expanded an empty Git email.
    user_agent = "Example Researcher "

    # Act and assert: both snapshot commands use this client factory.
    with pytest.raises(typer.BadParameter, match="name and email"):
        snapshot_client(user_agent, timeout=10)
