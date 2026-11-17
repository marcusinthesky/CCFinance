"""Check typed fan-out and the interpretation of independent model scores."""

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

import duckdb
import httpx
import httpx2
import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from pipeline.stages.processed.experiments.article_scoring import (
    _BodyReader,
    _frame,
    _Store,
    benchmark_article_labels,
    build_questions,
    interpret_answers,
    score_articles,
)
from pydantic import JsonValue
from pydantic_ai import ModelHTTPError
from pydantic_ai.models.decision import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionAnswer,
    DecisionModelSettings,
    DecisionRequest,
    DecisionResponse,
    NoulAnswer,
    NoulQuestion,
)
from pydantic_ai.models.system_one import SystemOneModel
from pydantic_ai.providers.system_one import SystemOneProvider


@pytest.mark.component
def test_companies_share_one_native_request_with_structured_questions() -> None:
    # Arrange: capture the actual provider transport without starting a model.
    bodies: list[dict[str, object]] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        bodies.append(body)
        answers: dict[str, object] = {}
        for name, question in body["questions"].items():
            if question["type"] == "noul":
                answers[name] = {"type": "noul", "noul": 0.99}
            else:
                options = list(question["criteria"])
                answers[name] = {
                    "type": "choice",
                    "choice": options[0],
                    "confidence": 1.0,
                    "probabilities": {
                        key: float(index == 0) for index, key in enumerate(options)
                    },
                }
        return httpx2.Response(
            200,
            json={
                "model": "kev-latest",
                "answers": answers,
                "usage": {"input_tokens": 123, "output_tokens": 0},
            },
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    model = SystemOneModel(
        "kev-latest",
        provider=SystemOneProvider(
            base_url="http://test.invalid",
            http_client=client,
        ),
    )
    candidates: list[dict[str, JsonValue]] = [
        {"issuer_id": "a", "name": "Alpha Inc."},
        {"issuer_id": "b", "name": "Beta Inc.", "tickers": ["BETA"]},
        {"issuer_id": "c", "name": None, "original_name": "Wrong Company"},
        {"issuer_id": "other-namespace:a", "name": "Alpha Inc."},
    ]

    # Act: ask the three binary questions through the real provider adapter.
    response = asyncio.run(
        model.decide(
            DecisionRequest(
                state={"article": "Alpha acquired Beta."},
                questions=build_questions(candidates),
            ),
            model_settings={},
        )
    )

    # Assert: one request keeps seven typed questions and defers unresolved identity.
    assert len(bodies) == 1
    assert len(response.answers) == 7
    sent = bodies[0]["questions"]
    assert isinstance(sent, dict)
    assert sent["c1.identity"]["instructions"] == (
        "Does this article mention the company Beta Inc. (BETA)?"
    )
    assert sent["c0.substantive"]["type"] == "noul"
    assert sent["c0.primary"]["instructions"] == (
        "Is Alpha Inc. one of the main subjects of this article?"
    )
    assert all(not key.startswith("c2.") for key in sent)
    assert all(not key.startswith("c3.") for key in sent)
    interpreted = interpret_answers(candidates, response.answers, 0.95)
    deferred = interpreted[2]
    assert deferred["status"] == "deferred_identity"
    assert deferred["identity_score"] is None
    assert interpreted[3] == interpreted[0] | {"issuer_id": "other-namespace:a"}


@pytest.mark.unit
@example(identity=0.99, substantive=0.9, primary=0.99)
@example(identity=0.99, substantive=0.01, primary=0.99)
@given(
    identity=st.floats(min_value=0, max_value=1),
    substantive=st.floats(min_value=0, max_value=1),
    primary=st.floats(min_value=0, max_value=1),
)
def test_binary_scores_preserve_raw_marginals_and_gate_published_primary(
    identity: float,
    substantive: float,
    primary: float,
) -> None:
    # Arrange: independent binary heads and a non-editorial article-kind annotation.
    candidate: list[dict[str, JsonValue]] = [{"issuer_id": "a", "name": "Alpha Inc."}]
    answers: dict[str, DecisionAnswer] = {
        "article_kind": ChoiceAnswer(
            choice="press_release",
            confidence=1,
            probabilities={
                "reporting": 0,
                "analysis_opinion": 0,
                "market_roundup": 0,
                "press_release": 1,
            },
        ),
        "c0.identity": NoulAnswer(noul=identity),
        "c0.substantive": NoulAnswer(noul=substantive),
        "c0.primary": NoulAnswer(noul=primary),
    }

    # Act: interpret the native scores under the configured identity threshold.
    row = interpret_answers(candidate, answers, 0.95)[0]

    # Assert: raw heads stay intact, inconsistencies stay visible, and identity gates.
    assert row["primary_score"] == (primary if identity >= 0.95 else None)
    assert row["raw_primary_score"] == primary
    assert row["substantive_score"] == row["relevance_score"] == substantive
    assert row["coverage_score"] == max(substantive, primary)
    flags = row["consistency_flags"]
    assert isinstance(flags, list)
    assert ("primary_exceeds_substantive" in flags) == (primary > substantive)
    assert ("substantive_exceeds_identity" in flags) == (substantive > identity)
    assert row["primary_tag"] == (primary >= 0.5)
    assert (row["status"] == "accepted") == (
        identity >= 0.95
        and (primary >= 0.95 or substantive >= 0.95)
        and not (primary >= 0.95 and substantive <= 1 - 0.95)
    )
    assert row["validation_status"] == "pending_human"


def _tiny_index(tmp_path: Path) -> tuple[Path, Path]:
    body = "Alpha reported increased sales."
    source = tmp_path / "source"
    source.mkdir()
    index = tmp_path / "index/shards/00000"
    index.mkdir(parents=True)
    records = [
        {
            "article_id": f"row-{row}",
            "source_article_id": f"original-{row}",
            "document_id": "body-id",
            "source_path": "a.parquet",
            "source_row": row,
            "text_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "title": title,
            "hostname": "news.example",
            "publish_date": "2020-01-01",
            "quality_flags": ["partial_company_catalog"],
            "candidates": [
                {
                    "issuer_id": "a",
                    "name": "Alpha Inc.",
                    "evidence_sources": ["name_alias"],
                    "uncertainty_flags": ["registry_names_not_historically_certified"],
                }
            ],
        }
        for row, title in enumerate(
            ("Alpha results", "A different headline", "Alpha results")
        )
    ]
    data = tmp_path / "index.jsonl"
    data.write_text("".join(json.dumps(row) + "\n" for row in records))
    with duckdb.connect() as con:
        con.execute(
            "COPY (SELECT $text AS text, {'source_id': n, 'byline': 'Reporter'} "
            "AS metadata FROM range(3) rows(n)) TO $file (FORMAT PARQUET)",
            {"text": body, "file": str(source / "a.parquet")},
        )
        con.execute(
            "COPY (SELECT * FROM read_json_auto($json)) TO $file (FORMAT PARQUET)",
            {"json": str(data), "file": str(index / "retained.parquet")},
        )
    (tmp_path / "index/manifest.json").write_text(
        json.dumps({"source_root": "../source"})
    )
    (tmp_path / "index/summary.json").write_text(json.dumps({"status": "complete"}))
    return tmp_path / "index", source


@pytest.mark.integration
def test_stream_preserves_source_copies_and_reuses_original_row_group(
    tmp_path: Path,
) -> None:
    # Arrange: equal bodies have two headlines and one exact inference duplicate.
    index, source = _tiny_index(tmp_path)
    body = "Alpha reported increased sales."

    # Act: stream source records and recover text and metadata in two batches.
    with _frame(index, None, 42) as (batches, count, requested):
        articles = [article for batch in batches for article in batch]
    with duckdb.connect() as con:
        reader = _BodyReader(source, con)
        first = reader.read(articles[:1])
        second = reader.read(articles[1:])

    # Assert: three source records keep two request identities and distinct metadata.
    assert count == requested == 3
    assert len({article.inference_id for article in articles}) == 2
    assert {article.title for article in articles} == {
        "Alpha results",
        "A different headline",
    }
    assert [original.text for original in first.values()] == [body]
    assert [original.text for original in second.values()] == [body, body]
    assert [original.metadata for original in first.values()] == [
        {"source_id": 0, "byline": "Reporter"}
    ]
    assert [original.metadata for original in second.values()] == [
        {"source_id": 1, "byline": "Reporter"},
        {"source_id": 2, "byline": "Reporter"},
    ]
    assert reader.groups_read == 1


@pytest.mark.integration
def test_retry_and_bounded_production_preserve_source_copies_and_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: one request is too long and a transient failure affects two copies.
    index, source = _tiny_index(tmp_path)
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps({"temperature": 1.0, "lora": 8}))
    params = tmp_path / "params.yaml"
    params.write_text(
        json.dumps(
            {
                "experiments": {
                    "article_labels": {
                        "deadline_utc": "2099-01-01T00:00:00Z",
                        "reserve_seconds": 0,
                        "model_revision": "a" * 40,
                        "base_revision": "b" * 40,
                        "runtime_manifest": str(runtime),
                        "benchmark_size": 3,
                    }
                }
            }
        )
    )
    calls: list[DecisionRequest] = []
    transient_failed = False

    async def metadata(self: httpx.AsyncClient, url: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "kev-latest",
                        "base": "Qwen/Qwen3.5-0.8B-Base",
                        "device": "cuda",
                        "backend": "torch",
                        "dtype": "bfloat16",
                        "max_state_tokens": 8192,
                        "truncate_states": False,
                        "temperature": 1.0,
                        "lora": 8,
                    }
                ]
            },
            request=httpx.Request("GET", url),
        )

    async def decide(
        self: SystemOneModel,
        request: DecisionRequest,
        model_settings: DecisionModelSettings,
    ) -> DecisionResponse:
        nonlocal transient_failed
        calls.append(request)
        if (
            isinstance(request.state, dict)
            and request.state["title"] == "A different headline"
        ):
            raise ModelHTTPError(
                status_code=422,
                model_name="kev-latest",
                body="state exceeds maximum tokens",
            )
        if not transient_failed:
            transient_failed = True
            raise ModelHTTPError(status_code=503, model_name="kev-latest", body="busy")
        answers: dict[str, DecisionAnswer] = {}
        for key, question in request.questions.items():
            if isinstance(question, NoulQuestion):
                answers[key] = NoulAnswer(noul=1)
            elif isinstance(question, ChoiceQuestion):
                chosen = "reporting" if key == "article_kind" else "central"
                answers[key] = ChoiceAnswer(
                    choice=chosen,
                    confidence=1,
                    probabilities={
                        option: float(option == chosen) for option in question.criteria
                    },
                )
        return DecisionResponse(answers=answers, model_name="kev-latest")

    monkeypatch.setattr(httpx.AsyncClient, "get", metadata)
    monkeypatch.setattr(SystemOneModel, "decide", decide)
    output = tmp_path / "output"

    # Act: retry the transient failure, then resume completed decisions and copies.
    with pytest.raises(RuntimeError, match="incomplete"):
        benchmark_article_labels(index, output, params)
    first = json.loads((output / "benchmark.json").read_text())
    benchmark_article_labels(index, output, params)
    resumed = json.loads((output / "benchmark.json").read_text())
    benchmark_article_labels(index, output, params)

    # Assert: one retry serves both copies, while admission failures remain unknown.
    assert len(calls) == 3
    assert first["requested"] == first["attempted"] == 3
    assert first["succeeded"] == first["completed"] == 0
    assert first["server_failed"] == 2
    assert first["context_deferred"] == 1
    assert first["status"] == "incomplete"
    assert resumed["succeeded"] == 2
    assert resumed["server_failed"] == 0
    assert resumed["status"] == "complete_with_unscorable"
    assert resumed["throughput_elapsed_seconds"] >= first["throughput_elapsed_seconds"]
    with duckdb.connect() as con:
        rows = con.execute(
            "SELECT article_id,status,primary_score FROM read_parquet(?) "
            "ORDER BY article_id",
            [str(output / "predictions.parquet")],
        ).fetchall()
    assert rows == [
        ("row-0", "accepted", 1),
        ("row-1", "too_long", None),
        ("row-2", "accepted", 1),
    ]

    # Arrange: move source resolution to an explicit CLI argument on another machine.
    (index / "manifest.json").write_text(json.dumps({"source_root": "/stale/source"}))
    original = index / "all.parquet"
    (index / "shards/00000/retained.parquet").rename(original)
    (index / "shards/00001").mkdir()
    with duckdb.connect() as con:
        for shard, condition in (
            ("00000", "source_row < 2"),
            ("00001", "source_row = 2"),
        ):
            source_rows = con.from_parquet(str(original)).filter(condition)
            source_rows.write_parquet(str(index / f"shards/{shard}/retained.parquet"))
    production = tmp_path / "production"

    # Act: commit bounded production Parquet and resume its completed chunk.
    score_articles(index, production, params, source=source)
    score_articles(index, production, params, source=source)

    # Assert: full JSON is cleared from SQLite; copies retain metadata and evidence.
    assert len(calls) == 5
    assert len(list((production / "chunks").glob("*.parquet"))) == 2
    assert not (production / "decisions.jsonl").exists()
    assert (production / "storage.json").exists()
    with duckdb.connect() as con:
        stored = con.execute(
            "SELECT article_id,json_extract_string(article_json,'$.source_article_id'),"
            "json_extract_string(article_json,'$.metadata.source_id'),"
            "json_extract_string(article_json,'$.candidates[0].uncertainty_flags[0]') "
            "FROM read_parquet(?) ORDER BY article_id",
            [str(production / "chunks/*.parquet")],
        ).fetchall()
    assert stored == [
        (
            f"row-{row}",
            f"original-{row}",
            str(row),
            "registry_names_not_historically_certified",
        )
        for row in range(3)
    ]

    with sqlite3.connect(production / "checkpoints.sqlite") as ledger:
        assert ledger.execute("SELECT count(*) FROM articles").fetchone() == (0,)
        assert ledger.execute(
            "SELECT count(*) FROM requests WHERE payload IS NOT NULL"
        ).fetchone() == (0,)

    # Arrange: realistic large pending decisions must not bloat the durable index.
    with _frame(index, None, 42) as (batches, _, _):
        template = next(batches)[0]
    with duckdb.connect() as con:
        original_body = _BodyReader(source, con).read([template])[template.article_id]
    store = _Store(production, production=True)
    try:
        previous_pointer = store.db.execute(
            "SELECT artifact FROM requests WHERE inference_id=?",
            [template.inference_id],
        ).fetchone()
        for number in range(64):
            article = template.model_copy(
                update={
                    "article_id": f"large-{number}",
                    "inference_id": f"request-{number}",
                }
            )
            store.save_decision(
                article.inference_id,
                {"status": "complete", "companies": [], "responses": ["x" * 3000]},
            )
            store.save_article(article, original_body, "00000002", number, reused=False)
        store.save_article(template, original_body, "00000002", 64, reused=True)
        store.db.commit()
        before_bytes = store.db.execute(
            "SELECT sum(pgsize) FROM dbstat WHERE name='requests'"
        ).fetchone()[0]

        # Act: flush only this bounded batch, preserving the earlier cache pointer.
        store.flush("00000002")

        # Assert: compact lookup storage drops transient JSON space and retains reuse.
        after_bytes = store.db.execute(
            "SELECT sum(pgsize) FROM dbstat WHERE name='requests'"
        ).fetchone()[0]
        assert after_bytes < before_bytes / 2
        assert store.db.execute(
            "SELECT count(*) FROM requests WHERE payload IS NOT NULL"
        ).fetchone() == (0,)
        assert (
            store.db.execute(
                "SELECT artifact FROM requests WHERE inference_id=?",
                [template.inference_id],
            ).fetchone()
            == previous_pointer
        )
        cached_decision = store.decision(template.inference_id)
        flushed_decision = store.decision("request-63")
        assert cached_decision is not None and cached_decision["status"] == "complete"
        assert flushed_decision is not None
        assert flushed_decision["responses"] == ["x" * 3000]
    finally:
        store.close()

    # Arrange: an expired operating deadline must not manufacture completed work.
    settings = json.loads(params.read_text())
    settings["experiments"]["article_labels"]["deadline_utc"] = "2000-01-01T00:00:00Z"
    params.write_text(json.dumps(settings))
    expired = tmp_path / "expired"

    # Act: stop before issuing decisions and preserve an explicit resumable status.
    with pytest.raises(RuntimeError, match="deadline_reached"):
        score_articles(index, expired, params, source=source)

    # Assert: attempted and succeeded both remain zero, with all source rows pending.
    stopped = json.loads((expired / "summary.json").read_text())
    assert stopped["attempted"] == stopped["completed"] == 0
    assert stopped["remaining"] == stopped["unattempted"] == 3
    assert len(calls) == 5
