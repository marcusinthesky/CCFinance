"""Check stratified link samples and cached, validated adjudication."""

import json
from pathlib import Path

import duckdb
import pytest
from pipeline.stages.processed.experiments.company_links import (
    Judge,
    Lookup,
    adjudicate,
    search,
)
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

UNIT = "2020-01--eng_Latn--part-000000--000.parquet"


def _write(con: duckdb.DuckDBPyConnection, query: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.sql(query).write_parquet(str(path))


def _sample(root: Path) -> None:
    with duckdb.connect() as con:
        _write(
            con,
            "SELECT 'a1' AS id, 0 AS start, 'Facebook' AS text, "
            "DATE '2019-05-01' AS day, 'x.com' AS host, 'T' AS title, "
            "'⟦Facebook⟧ fell' AS excerpt",
            root / "sample/mentions.parquet",
        )
        _write(
            con,
            "SELECT 'a1' AS id, DATE '2019-05-01' AS day, 'x.com' AS host, "
            "'T' AS title, 'Facebook fell' AS text",
            root / "sample/articles.parquet",
        )
        _write(
            con,
            "SELECT 1326801 AS cik, 'Meta Platforms, Inc.' AS name",
            root / "issuers/issuers.parquet",
        )
        _write(
            con,
            "SELECT 1326801 AS cik, 'FB' AS ticker, 'Nasdaq' AS exchange, "
            "DATE '2012-05-18' AS valid_from, DATE '2022-06-08' AS valid_to",
            root / "issuers/tickers.parquet",
        )
        _write(
            con,
            "SELECT 1326801 AS cik, * FROM (VALUES ('Facebook', 'facebook', "
            "'former_name'), ('FB', 'fb', 'ticker')) AS t(alias, key, source)",
            root / "issuers/aliases.parquet",
        )


@pytest.mark.component
@pytest.mark.parametrize("query", ["Facebook", "Facebook FB", "FB", "Facebook Inc"])
def test_search_finds_issuers_by_name_prefix_or_ticker(
    tmp_path: Path, query: str
) -> None:
    # Arrange: issuer tables with Meta under its former name and ticker.
    _sample(tmp_path)
    con = duckdb.connect()
    for table in ("issuers", "tickers", "aliases"):
        con.read_parquet(str(tmp_path / f"issuers/{table}.parquet")).create(table)

    # Act: search as a judge might, with names, tickers or both.
    found = search(Lookup(con, "2019-05-01"), query)

    # Assert: every form finds the issuer listed on that date.
    assert found == ["CIK 1326801: Meta Platforms, Inc. (FB Nasdaq)"]


@pytest.mark.integration
def test_adjudicate_retries_invalid_issuers_and_reuses_cache(tmp_path: Path) -> None:
    # Arrange: a primary model that first names an unlisted CIK, and an auditor.
    _sample(tmp_path)
    prompts: list[str] = []
    audits: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        prompts.append(str(messages[0]))
        args: dict[str, object] = {"decision": "listed", "role": "subject"}
        if "issuers" in tool.parameters_json_schema["properties"]:
            args = {"issuers": [{"name": "Meta", "cik": 1326801, "role": "subject"}]}
        elif any("Not listed" in str(message) for message in messages):
            args |= {"cik": 1326801, "rationale": "Facebook was Meta's 2019 name."}
        else:
            args |= {"cik": 9, "rationale": "A guess."}
        return ModelResponse(parts=[ToolCallPart(tool.name, args)])

    def audit(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        audits.append(info.output_tools[0].name)
        args = {"decision": "listed", "cik": 1326801, "role": "mentioned"}
        args |= {"rationale": "Facebook, now Meta."}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    def invalid(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        args = {"decision": "listed", "cik": 9, "role": "subject", "rationale": "x"}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    judges = [
        Judge("primary", FunctionModel(respond, model_name="p"), 1.0, articles=True),
        Judge("audit", FunctionModel(audit, model_name="a"), 1.0),
        Judge("repeat", FunctionModel(invalid, model_name="p"), 1.0),
    ]
    sample, issuers, labels = (
        tmp_path / name for name in ("sample", "issuers", "labels")
    )

    # Act: adjudicate twice; the second run should only read the cache.
    with models.override_allow_model_requests(False):
        pending = adjudicate(sample, issuers, judges, "low", 2, labels)
        calls = (len(prompts), len(audits))
        again = adjudicate(sample, issuers, judges, "low", 2, labels)

    # Assert: search results shown, invalid CIKs retried or recorded, none re-asked.
    assert (pending, again) == (0, 0)
    assert calls == (3, 1) == (len(prompts), len(audits))
    assert any("CIK 1326801: Meta Platforms, Inc. (FB Nasdaq)" in p for p in prompts)
    mentions = [
        json.loads(line)
        for line in (tmp_path / "labels/mentions.jsonl").read_text().splitlines()
    ]
    assert sorted((m["judge"], m["cik"], m["role"]) for m in mentions) == [
        ("audit", 1326801, "mentioned"),
        ("primary", 1326801, "subject"),
    ]
    assert '"role": "subject"' in (tmp_path / "labels/articles.jsonl").read_text()
