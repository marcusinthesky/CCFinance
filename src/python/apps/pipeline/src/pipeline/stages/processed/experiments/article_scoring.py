"""Score provisional article-company relationships through native decisions."""

import asyncio
import bisect
import hashlib
import json
import shutil
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import duckdb
import httpx
import typer
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from pydantic_ai.models.decision import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionAnswer,
    DecisionQuestion,
    DecisionRequest,
    NoulAnswer,
    NoulQuestion,
)
from pydantic_ai.models.system_one import SystemOneModel
from pydantic_ai.providers.system_one import SystemOneProvider

from pipeline.experiments.article_labels import ArticleLabelsConfig, load_config

JSON_VALUE_ADAPTER = TypeAdapter(JsonValue)
JSON_OBJECT_ADAPTER = TypeAdapter(dict[str, JsonValue])

COMPANY_QUESTIONS = {
    "identity": "Does this article mention the company {company}?",
    "substantive": (
        "Does this article provide meaningful information specifically about "
        "{company}, beyond merely mentioning it?"
    ),
    "primary": "Is {company} one of the main subjects of this article?",
}

ARTICLE_CRITERIA: dict[str, JsonValue] = {
    "reporting": {"definition": "Original editorial reporting of events and facts."},
    "analysis_opinion": {"definition": "Editorial analysis, commentary or opinion."},
    "market_roundup": {
        "definition": "Editorial coverage of several companies or markets."
    },
    "press_release": {"definition": "A company or agency's own announcement."},
    "promotional": {"definition": "Advertising, sponsored promotion or sales copy."},
    "non_article": {"definition": "Navigation, indexes or other non-article material."},
    "unresolved": {
        "definition": "The available text does not establish its article kind."
    },
}


class Article(BaseModel):
    """The compact CPU index supplies coordinates rather than copied article text."""

    model_config = ConfigDict(extra="allow")
    article_id: str
    document_id: str
    source_path: str
    source_row: int
    text_sha256: str
    title: str | None = None
    hostname: str
    publish_date: str | None = None
    candidates: list[dict[str, JsonValue]]
    inference_id: str


class _ServerInfo(BaseModel):
    """Validate the native endpoint's observable serving configuration."""

    model_config = ConfigDict(extra="ignore")
    name: str
    base: str
    device: str
    backend: str
    dtype: str
    max_state_tokens: int
    truncate_states: bool
    temperature: float
    lora: int


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_json(value) + "\n", encoding="utf-8")
    temporary.replace(path)


def _descriptor(candidate: dict[str, JsonValue]) -> str | None:
    """Use the resolved canonical name; preserve unsupported aliases as provenance."""
    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    tickers = candidate.get("tickers")
    if not isinstance(tickers, list) or not tickers:
        tickers = [candidate.get("ticker")]
    symbols = [symbol for symbol in tickers if isinstance(symbol, str) and symbol]
    return name + (" (" + ", ".join(symbols) + ")" if symbols else "")


def _question_sources(candidates: list[dict[str, JsonValue]]) -> dict[int, int]:
    """Share exact rendered questions while retaining every candidate namespace."""
    first: dict[str, int] = {}
    return {
        index: first.setdefault(descriptor, index)
        for index, candidate in enumerate(candidates)
        if (descriptor := _descriptor(candidate)) is not None
    }


def build_questions(
    candidates: list[dict[str, JsonValue]],
) -> dict[str, DecisionQuestion]:
    """Ask three independent binary questions with article kind as annotation."""
    questions: dict[str, DecisionQuestion] = {
        "article_kind": ChoiceQuestion(
            instructions={
                "question": "What kind of published material is this article?"
            },
            criteria=ARTICLE_CRITERIA,
        )
    }
    for index in sorted(set(_question_sources(candidates).values())):
        company = _descriptor(candidates[index])
        for dimension, instruction in COMPANY_QUESTIONS.items():
            questions[f"c{index}.{dimension}"] = NoulQuestion(
                instructions=instruction.format(company=company)
            )
    return questions


def interpret_answers(
    candidates: list[dict[str, JsonValue]],
    answers: dict[str, DecisionAnswer],
    threshold: float,
) -> list[dict[str, JsonValue]]:
    """Preserve raw marginals; accepted means an unvalidated model suggestion."""
    article_kind = answers["article_kind"]
    if not isinstance(article_kind, ChoiceAnswer):
        raise ValueError("The article-kind question did not return a Choice answer")
    editorial = sum(
        article_kind.probabilities[key]
        for key in ("reporting", "analysis_opinion", "market_roundup")
    )
    rows: list[dict[str, JsonValue]] = []
    sources = _question_sources(candidates)
    for index, candidate in enumerate(candidates):
        row: dict[str, JsonValue] = {
            "issuer_id": candidate["issuer_id"],
            "article_kind": article_kind.choice,
            "article_kind_probabilities": dict(article_kind.probabilities),
            "editorial_probability": editorial,
            "identity_score": None,
            "substantive_score": None,
            "raw_primary_score": None,
            "coverage_score": None,
            "identity_tag": None,
            "substantive_tag": None,
            "primary_tag": None,
            "coverage_tag": None,
            "primary_score": None,
            "relevance_score": None,
            "consistency_flags": [],
            "validation_status": "pending_human",
            "status": "deferred_identity",
        }
        if _descriptor(candidate) is None:
            row["consistency_flags"] = ["unresolved_company_name"]
            rows.append(row)
            continue
        marginals: dict[str, float] = {}
        for dimension in ("identity", "substantive", "primary"):
            answer = answers[f"c{sources[index]}.{dimension}"]
            if not isinstance(answer, NoulAnswer):
                raise ValueError("Company questions must return Noul answers")
            marginals[dimension] = answer.noul
        identity = marginals["identity"]
        substantive = marginals["substantive"]
        primary = marginals["primary"]
        coverage = max(substantive, primary)
        # These independent outputs are neither multiplied nor clamped into a joint.
        flags = [
            name
            for name, violation in (
                ("primary_exceeds_substantive", primary > substantive),
                ("substantive_exceeds_identity", substantive > identity),
                (
                    "strong_coverage_contradiction",
                    primary >= threshold and substantive <= 1 - threshold,
                ),
            )
            if violation
        ]
        status = "review"
        if (
            identity >= threshold
            and coverage >= threshold
            and "strong_coverage_contradiction" not in flags
        ):
            status = "accepted"
        elif identity <= 1 - threshold:
            status = "rejected"
        row.update(
            {
                "identity_score": identity,
                "substantive_score": substantive,
                "raw_primary_score": primary,
                # Primary coverage entails substantive coverage. This maximum is a
                # deterministic ranking rule, not a calibrated union probability.
                "coverage_score": coverage,
                "identity_tag": identity >= 0.5,
                "substantive_tag": substantive >= 0.5,
                "primary_tag": primary >= 0.5,
                "coverage_tag": primary >= 0.5 or substantive >= 0.5,
                "primary_score": primary if identity >= threshold else None,
                "relevance_score": substantive,
                "consistency_flags": flags,
                "status": status,
            }
        )
        rows.append(row)
    return rows


class _BodyReader:
    """Read and retain one bounded original row group across consecutive batches."""

    def __init__(self, source: Path, con: duckdb.DuckDBPyConnection) -> None:
        self.source = source
        self.con = con
        self.bounds: dict[str, list[tuple[int, int, int]]] = {}
        self.cached_group: tuple[str, int] | None = None
        self.cached_rows: dict[int, tuple[str, str | None]] = {}
        self.groups_read = 0

    def read(self, articles: list[Article]) -> dict[str, "_Body"]:
        result: dict[str, _Body] = {}
        groups: dict[tuple[str, int], list[Article]] = {}
        for article in articles:
            if article.source_path not in self.bounds:
                metadata = self.con.execute(
                    "SELECT row_group_id,max(row_group_num_rows),"
                    "sum(total_uncompressed_size) FILTER (WHERE path_in_schema='text') "
                    "FROM parquet_metadata(?) GROUP BY row_group_id "
                    "ORDER BY row_group_id",
                    [str(self.source / article.source_path)],
                ).fetchall()
                offset = 0
                bounds = []
                for _, rows, size in metadata:
                    bounds.append((offset, offset + int(rows), int(size or 0)))
                    offset += int(rows)
                self.bounds[article.source_path] = bounds
            bounds = self.bounds[article.source_path]
            index = bisect.bisect_right([b[0] for b in bounds], article.source_row) - 1
            if index < 0 or article.source_row >= bounds[index][1]:
                raise ValueError(
                    f"Source row outside original file: {article.article_id}"
                )
            groups.setdefault((article.source_path, index), []).append(article)
        for (file, index), members in groups.items():
            lower, upper, size = self.bounds[file][index]
            if self.cached_group != (file, index):
                if size > 128 * 1024 * 1024:
                    rows = self.con.execute(
                        "SELECT file_row_number,text,to_json(metadata) "
                        "FROM read_parquet("
                        "$file,file_row_number=true) WHERE file_row_number "
                        "IN (SELECT unnest($rows))",
                        {
                            "file": str(self.source / file),
                            "rows": [article.source_row for article in members],
                        },
                    ).fetchall()
                    self.cached_group = None
                else:
                    rows = self.con.execute(
                        "SELECT file_row_number,text,to_json(metadata) "
                        "FROM read_parquet("
                        "$file,file_row_number=true) "
                        "WHERE file_row_number >= $lower "
                        "AND file_row_number < $upper",
                        {
                            "file": str(self.source / file),
                            "lower": lower,
                            "upper": upper,
                        },
                    ).fetchall()
                    self.cached_group = (file, index)
                self.groups_read += 1
                self.cached_rows = {
                    int(row): (text, metadata) for row, text, metadata in rows
                }
            for article in members:
                original = self.cached_rows.get(article.source_row)
                if original is None or not isinstance(original[0], str):
                    raise ValueError(f"Original text missing for {article.article_id}")
                text, metadata_json = original
                if hashlib.sha256(text.encode()).hexdigest() != article.text_sha256:
                    raise ValueError(f"Text checksum changed for {article.article_id}")
                metadata = (
                    JSON_VALUE_ADAPTER.validate_json(metadata_json)
                    if metadata_json is not None
                    else None
                )
                result[article.article_id] = _Body(text, metadata)
        return result


@dataclass(frozen=True)
class _Body:
    text: str
    metadata: JsonValue


def _resolve_source(
    input: Path, manifest: dict[str, JsonValue], source: Path | None
) -> Path:
    if source is not None:
        return source.resolve()
    value = manifest.get("source_root")
    if not isinstance(value, str):
        raise ValueError("Pass --source or provide source_root in the CPU manifest")
    path = Path(value)
    return (path if path.is_absolute() else input / path).resolve()


def _article_batches(
    con: duckdb.DuckDBPyConnection, files: list[Path], *, identities: bool
) -> Iterator[list[Article]]:
    for file in files:
        query = (
            "SELECT to_json(i) FROM read_parquet(?) i ORDER BY source_path,source_row"
        )
        if identities:
            query = (
                "SELECT to_json(i) FROM (SELECT *, sha256(to_json(struct_pack("
                "body:=text_sha256,title:=title,date:=publish_date,publisher:=hostname,"
                "candidates:=candidates))) AS inference_id FROM read_parquet(?)) i "
                "ORDER BY source_path,source_row"
            )
        con.execute(query, [str(file)])
        while rows := con.fetchmany(4096):
            yield [Article.model_validate_json(row[0]) for row in rows]


@contextmanager
def _frame(
    input: Path, limit: int | None, seed: int, selection: Path | None = None
) -> Iterator[tuple[Iterator[list[Article]], int, int]]:
    with duckdb.connect() as con:
        con.execute("SET memory_limit='2GB'")
        con.execute("SET threads=1")
        con.execute("SET preserve_insertion_order=false")
        con.execute("SET max_temp_directory_size='4GB'")
        files = sorted(input.glob("shards/*/retained.parquet"))
        if not files:
            raise ValueError("The CPU index has no completed retained shards")
        if limit is None:
            count = int(
                con.from_parquet([str(path) for path in files]).count("*").fetchone()[0]
            )
            yield _article_batches(con, files, identities=True), count, count
            return
        frame_metadata = selection.with_suffix(".json") if selection else None
        if (
            selection
            and selection.exists()
            and frame_metadata
            and frame_metadata.exists()
        ):
            saved = json.loads(frame_metadata.read_text())
            if saved["seed"] != seed or saved["requested"] != min(
                limit, saved["frame_documents"]
            ):
                raise ValueError("Frozen selection differs from the requested sample")
            if (
                hashlib.sha256(selection.read_bytes()).hexdigest()
                != saved["selection_sha256"]
            ):
                raise ValueError("Frozen selection checksum changed")
            yield (
                _article_batches(con, [selection], identities=False),
                int(saved["frame_documents"]),
                int(saved["requested"]),
            )
            return
        con.read_parquet([str(path) for path in files]).create_view("input_records")
        if limit is not None:
            count_row = con.execute("SELECT count(*) FROM input_records").fetchone()
            if count_row is None:
                raise ValueError("The retained article population is missing")
            count = int(count_row[0])
            con.execute(
                "CREATE TEMP TABLE sample_keys AS SELECT "
                "article_id,source_path,source_row "
                "FROM input_records ORDER BY sha256($seed||':'||article_id),article_id "
                "LIMIT $limit",
                {"seed": str(seed), "limit": limit},
            )
            con.execute(
                "CREATE VIEW chosen AS SELECT i.* FROM input_records i "
                "JOIN sample_keys s "
                "USING(article_id,source_path,source_row)"
            )
        else:
            con.execute("CREATE VIEW chosen AS SELECT * FROM input_records")
        con.execute(
            "CREATE VIEW identities AS SELECT *, sha256(to_json(struct_pack("
            "body:=text_sha256,title:=title,date:=publish_date,publisher:=hostname,"
            "candidates:=candidates))) AS inference_id FROM chosen"
        )
        con.execute(
            "CREATE VIEW selected AS SELECT inference_id,article_id FROM identities"
        )
        unit_count = min(count, limit)
        query = (
            "SELECT to_json(i) FROM identities i "
            "JOIN selected s USING(inference_id,article_id) "
            "ORDER BY source_path,source_row"
        )
        requested = unit_count
        if selection:
            con.execute(
                "COPY (SELECT i.* FROM identities i JOIN selected s "
                "USING(inference_id,article_id) ORDER BY source_path,source_row) "
                "TO $output (FORMAT PARQUET)",
                {"output": str(selection.with_suffix(".parquet.tmp"))},
            )
            selection.with_suffix(".parquet.tmp").replace(selection)
            if frame_metadata:
                _write_json(
                    frame_metadata,
                    {
                        "frame_documents": count,
                        "requested": requested,
                        "seed": seed,
                        "selection": "SHA256(seed:article_id) retained-row priority",
                        "frame_unit": "retained source article rows",
                        "selection_sha256": hashlib.sha256(
                            selection.read_bytes()
                        ).hexdigest(),
                    },
                )
            con.execute(
                "SELECT to_json(s) FROM read_parquet(?) s "
                "ORDER BY source_path,source_row",
                [str(selection)],
            )
        else:
            con.execute(query)
        if selection:
            yield _article_batches(con, [selection], identities=False), count, requested
        else:

            def batches() -> Iterator[list[Article]]:
                while rows := con.fetchmany(4096):
                    yield [Article.model_validate_json(row[0]) for row in rows]

            yield batches(), count, requested


async def _score(
    article: Article, text: str, config: ArticleLabelsConfig, model: SystemOneModel
) -> dict[str, JsonValue]:
    state: JsonValue = {
        "title": article.title,
        "published_at": article.publish_date,
        "publisher": article.hostname,
        "article": text,
    }
    candidates = {str(item["issuer_id"]): item for item in article.candidates}
    unique = list(candidates.values())
    sources = _question_sources(unique)
    representatives = [
        candidate
        for index, candidate in enumerate(unique)
        if sources.get(index, index) == index
    ]
    rows: dict[str, dict[str, JsonValue]] = {}
    responses: list[JsonValue] = []
    request_hashes: list[JsonValue] = []
    input_tokens = 0
    started = time.monotonic()
    for offset in range(0, len(representatives), config.max_candidates_per_request):
        batch = representatives[offset : offset + config.max_candidates_per_request]
        questions = build_questions(batch)
        request = DecisionRequest(state=state, questions=questions)
        # The request identity includes every native structured question and its rubric.
        request_hashes.append(
            hashlib.sha256(_json(asdict(request)).encode()).hexdigest()
        )
        response = await model.decide(
            request, model_settings={"timeout": config.request_timeout_seconds}
        )
        responses.append(json.loads(_json(asdict(response))))
        typed: dict[str, DecisionAnswer] = {}
        for name, answer in response.answers.items():
            if not isinstance(answer, NoulAnswer | ChoiceAnswer):
                raise ValueError(f"Unexpected answer kind: {name}")
            typed[name] = answer
        for row in interpret_answers(batch, typed, config.min_probability):
            rows[str(row["issuer_id"])] = row
        input_tokens += response.usage.input_tokens
    return {
        "status": "complete",
        "companies": [
            rows[str(unique[sources.get(index, index)]["issuer_id"])]
            | {"issuer_id": candidate["issuer_id"]}
            for index, candidate in enumerate(unique)
        ],
        "request_sha256": request_hashes,
        "responses": responses,
        "input_tokens": input_tokens,
        "elapsed_seconds": time.monotonic() - started,
        "model_name": config.api_model,
    }


class _Store:
    """Keep request identities in SQLite and bounded production payloads in Parquet."""

    def __init__(self, output: Path, *, production: bool) -> None:
        self.output = output
        self.production = production
        self.source_files_total = 0
        progress = output / "progress.json"
        self.last_source: JsonValue = (
            json.loads(progress.read_text()).get("last_source")
            if progress.exists()
            else None
        )
        self.db = sqlite3.connect(output / "checkpoints.sqlite")
        self.reader = duckdb.connect(config={"memory_limit": "512MB", "threads": 1})
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS requests(inference_id TEXT PRIMARY KEY, "
            "status TEXT NOT NULL,artifact TEXT,payload TEXT);"
            "CREATE TABLE IF NOT EXISTS articles(article_id TEXT PRIMARY KEY, "
            "inference_id TEXT NOT NULL,chunk_key TEXT NOT NULL,position INTEGER, "
            "article_json TEXT NOT NULL,reused INTEGER NOT NULL);"
            "CREATE TABLE IF NOT EXISTS chunks(chunk_key TEXT PRIMARY KEY, "
            "artifact TEXT NOT NULL,records INTEGER,succeeded INTEGER, "
            "context_deferred INTEGER,server_failed INTEGER,"
            "reused INTEGER,bytes INTEGER);"
            "CREATE TABLE IF NOT EXISTS clock(seconds REAL,"
            "preparation REAL,attempts INTEGER);"
            "INSERT INTO clock SELECT 0,0,0 WHERE NOT EXISTS(SELECT 1 FROM clock);"
            "CREATE TABLE IF NOT EXISTS failures(attempt INTEGER PRIMARY KEY, "
            "inference_id TEXT,status TEXT,error TEXT,recorded_at TEXT);"
        )

    def close(self) -> None:
        self.reader.close()
        self.db.close()

    def decision(
        self, inference_id: str, *, terminal: bool = True
    ) -> dict[str, JsonValue] | None:
        row = self.db.execute(
            "SELECT status,artifact,payload FROM requests WHERE inference_id=?",
            [inference_id],
        ).fetchone()
        if row is None or (terminal and row[0] not in ("complete", "too_long")):
            return None
        if row[2] is not None:
            return JSON_OBJECT_ADAPTER.validate_json(row[2])
        result = self.reader.execute(
            "SELECT decision_json FROM read_parquet(?) WHERE inference_id=? LIMIT 1",
            [str(self.output / row[1]), inference_id],
        ).fetchone()
        if result is None:
            raise ValueError("A committed request is missing from its decision chunk")
        return JSON_OBJECT_ADAPTER.validate_json(result[0])

    def save_decision(self, inference_id: str, decision: dict[str, JsonValue]) -> None:
        self.db.execute(
            "INSERT INTO requests VALUES (?,?,NULL,?) ON CONFLICT(inference_id) "
            "DO UPDATE SET status=excluded.status,artifact=NULL,"
            "payload=excluded.payload",
            [inference_id, decision["status"], _json(decision)],
        )
        self.db.execute("UPDATE clock SET attempts=attempts+1")
        if decision["status"] != "complete":
            self.db.execute(
                "INSERT INTO failures SELECT attempts,?,?,?,? FROM clock",
                [
                    inference_id,
                    decision["status"],
                    str(decision.get("error")),
                    datetime.now(UTC).isoformat(),
                ],
            )

    def save_article(
        self, article: Article, body: _Body, chunk: str, position: int, *, reused: bool
    ) -> None:
        provenance = article.model_dump(mode="json") | {"metadata": body.metadata}
        self.last_source = {
            "path": article.source_path,
            "row": article.source_row,
            "article_id": article.article_id,
        }
        self.db.execute(
            "INSERT INTO articles VALUES (?,?,?,?,?,?) ON CONFLICT(article_id) "
            "DO UPDATE SET inference_id=excluded.inference_id,"
            "chunk_key=excluded.chunk_key,"
            "position=excluded.position,article_json=excluded.article_json,reused=excluded.reused",
            [
                article.article_id,
                article.inference_id,
                chunk,
                position,
                _json(provenance),
                reused,
            ],
        )

    def finished(self, chunk: str, expected: int) -> bool:
        row = self.db.execute(
            "SELECT records,server_failed FROM chunks WHERE chunk_key=?", [chunk]
        ).fetchone()
        return row is not None and row[0] == expected and row[1] == 0

    def begin(self, chunk: str) -> None:
        saved = self.db.execute(
            "SELECT artifact FROM chunks WHERE chunk_key=?", [chunk]
        ).fetchone()
        if saved is None:
            return
        rows = self.reader.execute(
            "SELECT article_id,inference_id,chunk_position,"
            "article_json,decision_reused "
            "FROM read_parquet(?)",
            [str(self.output / saved[0])],
        ).fetchall()
        self.db.executemany(
            "INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?)",
            [(row[0], row[1], chunk, row[2], row[3], row[4]) for row in rows],
        )
        self.db.execute("DELETE FROM chunks WHERE chunk_key=?", [chunk])
        self.db.commit()

    def records(
        self, chunk: str | None = None
    ) -> Iterator[tuple[dict[str, JsonValue], dict[str, JsonValue], int, bool]]:
        query = "SELECT inference_id,article_json,position,reused FROM articles"
        parameters = []
        if chunk is not None:
            query += " WHERE chunk_key=?"
            parameters.append(chunk)
        query += " ORDER BY chunk_key,position"
        for inference_id, provenance, position, reused in self.db.execute(
            query, parameters
        ):
            decision = self.decision(inference_id, terminal=False)
            if decision is None:
                raise ValueError("An article checkpoint is missing its request result")
            yield (
                JSON_OBJECT_ADAPTER.validate_json(provenance),
                decision,
                position,
                bool(reused),
            )

    def flush(self, chunk: str) -> None:
        if not self.production:
            return
        directory = self.output / "chunks"
        directory.mkdir(exist_ok=True)
        artifact = directory / f"{chunk}.parquet"
        staging = artifact.with_suffix(".jsonl.tmp")
        counts = {
            "records": 0,
            "succeeded": 0,
            "context_deferred": 0,
            "server_failed": 0,
            "reused": 0,
        }
        identities: set[str] = set()
        with staging.open("w", encoding="utf-8") as handle:
            for article, decision, position, reused in self.records(chunk):
                identities.add(str(article["inference_id"]))
                counts["records"] += 1
                counts[
                    "succeeded"
                    if decision["status"] == "complete"
                    else "context_deferred"
                    if decision["status"] == "too_long"
                    else "server_failed"
                ] += 1
                counts["reused"] += int(reused)
                handle.write(
                    _json(
                        {
                            **{
                                key: article[key]
                                for key in (
                                    "article_id",
                                    "document_id",
                                    "inference_id",
                                    "source_path",
                                    "source_row",
                                )
                            },
                            "chunk_position": position,
                            "status": decision["status"],
                            "decision_reused": reused,
                            "article_json": _json(article),
                            "decision_json": _json(decision),
                        }
                    )
                    + "\n"
                )
        if not counts["records"]:
            staging.unlink()
            return
        self.reader.execute(
            "COPY (SELECT * REPLACE(cast(article_json AS JSON) AS article_json, "
            "cast(decision_json AS JSON) AS decision_json) "
            "FROM read_json_auto($json)) "
            "TO $output (FORMAT PARQUET, COMPRESSION ZSTD)",
            {"json": str(staging), "output": str(artifact.with_suffix(".parquet.tmp"))},
        )
        artifact.with_suffix(".parquet.tmp").replace(artifact)
        staging.unlink()
        relative = str(artifact.relative_to(self.output))
        compact_requests = []
        for inference_id in identities:
            request = self.db.execute(
                "SELECT status FROM requests WHERE inference_id=? "
                "AND (payload IS NOT NULL OR artifact=?)",
                [inference_id, relative],
            ).fetchone()
            if request is not None:
                compact_requests.append((inference_id, request[0], relative, None))
        # Remove the whole flushed batch before reinserting compact lookup rows.
        # Shrinking JSON with UPDATE leaves sparse leaf pages in the permanent index.
        self.db.executemany(
            "DELETE FROM requests WHERE inference_id=?",
            [(request[0],) for request in compact_requests],
        )
        self.db.executemany("INSERT INTO requests VALUES (?,?,?,?)", compact_requests)
        self.db.execute(
            "INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?)",
            [
                chunk,
                relative,
                counts["records"],
                counts["succeeded"],
                counts["context_deferred"],
                counts["server_failed"],
                counts["reused"],
                artifact.stat().st_size,
            ],
        )
        self.db.execute("DELETE FROM articles WHERE chunk_key=?", [chunk])
        self.db.commit()

    def counts(self) -> dict[str, int]:
        committed = self.db.execute(
            "SELECT coalesce(sum(records),0),coalesce(sum(succeeded),0),"
            "coalesce(sum(context_deferred),0),coalesce(sum(server_failed),0),"
            "coalesce(sum(reused),0),coalesce(sum(bytes),0) FROM chunks"
        ).fetchone()
        pending = self.db.execute(
            "SELECT count(*),coalesce(sum(r.status='complete'),0),"
            "coalesce(sum(r.status='too_long'),0),coalesce(sum(r.status='server_failed'),0),"
            "coalesce(sum(a.reused),0) FROM articles a "
            "JOIN requests r USING(inference_id)"
        ).fetchone()
        return {
            name: int(committed[index] + pending[index])
            for index, name in enumerate(
                (
                    "attempted",
                    "completed",
                    "context_deferred",
                    "server_failed",
                    "reused_source_records",
                )
            )
        } | {"decision_chunk_bytes": int(committed[5])}


def _export(store: _Store, output: Path) -> None:
    jsonl = output / "decisions.jsonl.tmp"
    pairs_path = output / "company-decisions.jsonl.tmp"
    pair_count = 0
    with (
        jsonl.open("w", encoding="utf-8") as documents,
        pairs_path.open("w", encoding="utf-8") as pairs,
    ):
        for article, decision, _, reused in store.records():
            document = article | decision | {"decision_reused": reused}
            documents.write(_json(document) + "\n")
            candidates = {
                str(candidate["issuer_id"]): candidate
                for candidate in article.get("candidates", [])
                if isinstance(candidate, dict)
            }
            for company in document.get("companies", []):
                if not isinstance(company, dict):
                    raise ValueError("Company decisions must be mappings")
                pair = {
                    **company,
                    "article_id": document["article_id"],
                    "document_id": document["document_id"],
                    "inference_id": document["inference_id"],
                    "article": {
                        key: value
                        for key, value in article.items()
                        if key != "candidates"
                    },
                    "candidate": candidates[str(company["issuer_id"])],
                    "request_sha256": decision.get("request_sha256"),
                    "model_name": decision.get("model_name"),
                }
                pairs.write(_json(pair) + "\n")
                pair_count += 1
    jsonl.replace(output / "decisions.jsonl")
    if pair_count:
        with duckdb.connect() as con:
            con.execute(
                "COPY (SELECT * FROM read_json_auto($json, "
                "format='newline_delimited')) "
                "TO $out (FORMAT PARQUET)",
                {
                    "json": str(pairs_path),
                    "out": str(output / "predictions.parquet.tmp"),
                },
            )
        (output / "predictions.parquet.tmp").replace(output / "predictions.parquet")
    pairs_path.unlink()


def _failure(article: Article, error: Exception) -> dict[str, JsonValue]:
    status = (
        "too_long"
        if getattr(error, "status_code", None) == 422 and "token" in str(error).lower()
        else "server_failed"
    )
    return {
        "status": status,
        "error": str(error),
        "companies": [
            {
                "issuer_id": candidate["issuer_id"],
                "status": status if _descriptor(candidate) else "deferred_identity",
                "identity_score": None,
                "substantive_score": None,
                "raw_primary_score": None,
                "coverage_score": None,
                "identity_tag": None,
                "substantive_tag": None,
                "primary_tag": None,
                "coverage_tag": None,
                "relevance_score": None,
                "primary_score": None,
                "consistency_flags": []
                if _descriptor(candidate)
                else ["unresolved_company_name"],
                "validation_status": "pending_human",
            }
            for candidate in article.candidates
        ],
    }


async def _check_server(config: ArticleLabelsConfig, output: Path) -> None:
    profile = JSON_OBJECT_ADAPTER.validate_json(config.runtime_manifest.read_bytes())
    for key, expected in (
        ("api_model", config.api_model),
        ("base_model", config.base_model),
        ("model", config.model),
        ("model_revision", config.model_revision),
        ("base_revision", config.base_revision),
        ("max_context_tokens", config.max_context_tokens),
    ):
        if key in profile and profile[key] != expected:
            raise ValueError(f"Configured {key} differs from the runtime profile")
    async with httpx.AsyncClient(timeout=config.request_timeout_seconds) as client:
        response = await client.get(f"{config.server_url.rstrip('/')}/v1/models")
        response.raise_for_status()
        reported = response.json()
    servers = [_ServerInfo.model_validate(row) for row in reported["models"]]
    server = next((row for row in servers if row.name == config.api_model), None)
    if server is None:
        raise ValueError("The server does not advertise the configured model alias")
    expected_fields: dict[str, JsonValue] = {
        "base": config.base_model,
        "max_state_tokens": config.max_context_tokens,
        "truncate_states": profile.get("truncate_states", False),
    }
    for key in ("device", "backend", "dtype", "lora"):
        if key in profile:
            expected_fields[key] = profile[key]
    observed = server.model_dump(mode="json")
    if any(observed[key] != value for key, value in expected_fields.items()):
        raise ValueError("Native server metadata differs from the runtime profile")
    temperature = profile.get("temperature")
    if (
        not isinstance(temperature, int | float)
        or abs(server.temperature - temperature) > 1e-9
    ):
        raise ValueError("Native server calibration differs from the runtime profile")
    _write_json(output / "server.json", reported)


def _progress(store: _Store, requested: int, elapsed: float) -> dict[str, JsonValue]:
    counts = store.counts()
    return {
        **counts,
        "requested": requested,
        "succeeded": counts["completed"],
        "unattempted": max(0, requested - counts["attempted"]),
        "remaining": max(
            0, requested - counts["completed"] - counts["context_deferred"]
        ),
        "elapsed_seconds": elapsed,
        "source_record_chunks_committed": int(
            store.db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        ),
        "source_files_total": store.source_files_total,
        "last_source": store.last_source,
    }


def _storage_projection(store: _Store, population: int) -> dict[str, JsonValue]:
    counts = store.counts()
    page_size = int(store.db.execute("PRAGMA page_size").fetchone()[0])
    used_pages = int(store.db.execute("PRAGMA page_count").fetchone()[0]) - int(
        store.db.execute("PRAGMA freelist_count").fetchone()[0]
    )
    observed = counts["attempted"]
    measured_bytes = counts["decision_chunk_bytes"] + used_pages * page_size
    bytes_per_record = measured_bytes / observed if observed else None
    remaining = max(0, population - observed)
    return {
        "observed_source_records": observed,
        "compressed_chunk_bytes": counts["decision_chunk_bytes"],
        "active_sqlite_bytes": used_pages * page_size,
        "conditional_bytes_per_source_record": bytes_per_record,
        "conditional_remaining_bytes": remaining * bytes_per_record
        if bytes_per_record is not None
        else None,
        "filesystem_free_bytes": shutil.disk_usage(store.output).free,
        "basis": (
            "Current compressed chunks and active SQLite pages; "
            "conditional on comparable later records"
        ),
    }


async def _run(
    input: Path, output: Path, params: Path, benchmark: bool, source: Path | None = None
) -> None:
    config = load_config(params)
    summary = json.loads((input / "summary.json").read_text())
    if summary.get("status") != "complete":
        raise ValueError("Inference requires a completed CPU index")
    output.mkdir(parents=True, exist_ok=True)
    cpu_manifest = JSON_OBJECT_ADAPTER.validate_json(
        (input / "manifest.json").read_bytes()
    )
    source_root = _resolve_source(input, cpu_manifest, source)
    contract = {
        "config": config.model_dump(mode="json"),
        "runtime": json.loads(config.runtime_manifest.read_text()),
        "rubric": {
            "name": "independent-binary-v1",
            "company_questions": COMPANY_QUESTIONS,
            "article_kind": ARTICLE_CRITERIA,
            "coverage_score": "max(substantive_score, raw_primary_score)",
            "interpretation": (
                "Independent model marginals, not calibrated joint probabilities. "
                "Coverage is a ranking rule; "
                "acceptance remains pending human validation."
            ),
        },
        "cpu": cpu_manifest,
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "benchmark": benchmark,
        "storage": "benchmark-readable"
        if benchmark
        else "compressed-source-record-chunks",
    }
    operational = {
        "deadline_utc",
        "reserve_seconds",
        "concurrency",
        "request_timeout_seconds",
        "server_url",
        "runtime_manifest",
    }
    identity_contract = contract | {
        "config": config.model_dump(mode="json", exclude=operational)
    }
    fingerprint = hashlib.sha256(_json(identity_contract).encode()).hexdigest()
    manifest_path = output / "manifest.json"
    if (
        manifest_path.exists()
        and json.loads(manifest_path.read_text())["contract_sha256"] != fingerprint
    ):
        raise ValueError("Scoring inputs changed; use a new output directory")
    _write_json(manifest_path, {**contract, "contract_sha256": fingerprint})
    _write_json(
        output / "source.json",
        {
            "resolved_source": str(source_root),
            "source_override": str(source) if source is not None else None,
            "body_verification": "SHA256 checked against the immutable CPU index",
        },
    )
    await _check_server(config, output)
    model = SystemOneModel(
        config.api_model, provider=SystemOneProvider(base_url=config.server_url)
    )
    store = _Store(output, production=not benchmark)
    store.source_files_total = len(list(input.glob("shards/*/retained.parquet")))
    saved_clock = store.db.execute("SELECT seconds,preparation FROM clock").fetchone()
    prior_seconds, prior_preparation = float(saved_clock[0]), float(saved_clock[1])
    deadline = config.deadline_utc.timestamp() - config.reserve_seconds
    started = time.monotonic()
    stopped_for_storage = False
    deadline_reached = False
    try:
        with (
            _frame(
                input,
                config.benchmark_size if benchmark else None,
                config.seed,
                output / "selection.parquet" if benchmark else None,
            ) as (chunks, frame_count, requested),
            duckdb.connect(config={"memory_limit": "1GB", "threads": 1}) as con,
        ):
            scoring_started = time.monotonic()
            preparation_seconds = prior_preparation + scoring_started - started
            store.db.execute("UPDATE clock SET preparation=?", [preparation_seconds])
            store.db.commit()
            reader = _BodyReader(source_root, con)
            semaphore = asyncio.Semaphore(config.concurrency)
            if datetime.now(UTC).timestamp() >= deadline:
                deadline_reached = True
                chunks = iter(())

            async def score_one(
                article: Article, text: str
            ) -> tuple[Article, dict[str, JsonValue] | None]:
                async with semaphore:
                    if datetime.now(UTC).timestamp() >= deadline:
                        return article, None
                    try:
                        return article, await _score(article, text, config, model)
                    except Exception as error:
                        return article, _failure(article, error)

            for chunk_number, articles in enumerate(chunks):
                key = f"{chunk_number:08d}"
                if store.production and store.finished(key, len(articles)):
                    continue
                if datetime.now(UTC).timestamp() >= deadline:
                    deadline_reached = True
                    break
                store.begin(key)
                for offset in range(0, len(articles), 32):
                    pending = []
                    for position, article in enumerate(
                        articles[offset : offset + 32], start=offset
                    ):
                        saved = store.db.execute(
                            "SELECT r.status FROM articles a "
                            "JOIN requests r USING(inference_id) "
                            "WHERE a.article_id=?",
                            [article.article_id],
                        ).fetchone()
                        if saved is None or saved[0] not in ("complete", "too_long"):
                            pending.append((position, article))
                    bodies = reader.read([article for _, article in pending])
                    groups: dict[str, list[tuple[int, Article]]] = {}
                    for position, article in pending:
                        groups.setdefault(article.inference_id, []).append(
                            (position, article)
                        )
                    tasks = []
                    for inference_id, members in groups.items():
                        cached = store.decision(inference_id)
                        if cached is not None:
                            for position, article in members:
                                store.save_article(
                                    article,
                                    bodies[article.article_id],
                                    key,
                                    position,
                                    reused=True,
                                )
                        else:
                            article = members[0][1]
                            tasks.append(
                                score_one(article, bodies[article.article_id].text)
                            )
                    for task in asyncio.as_completed(tasks):
                        representative, decision = await task
                        if decision is None:
                            deadline_reached = True
                            continue
                        store.save_decision(representative.inference_id, decision)
                        for member_number, (position, article) in enumerate(
                            groups[representative.inference_id]
                        ):
                            store.save_article(
                                article,
                                bodies[article.article_id],
                                key,
                                position,
                                reused=member_number > 0,
                            )
                    elapsed = prior_seconds + time.monotonic() - scoring_started
                    store.db.execute("UPDATE clock SET seconds=?", [elapsed])
                    store.db.commit()
                    _write_json(
                        output / "progress.json", _progress(store, requested, elapsed)
                    )
                    if deadline_reached:
                        break
                store.flush(key)
                if store.production:
                    storage = _storage_projection(store, requested)
                    _write_json(output / "storage.json", storage)
                    required = storage["conditional_remaining_bytes"]
                    available = storage["filesystem_free_bytes"]
                    if (
                        isinstance(required, int | float)
                        and isinstance(available, int)
                        and required > available
                    ):
                        stopped_for_storage = True
                        break
                if deadline_reached:
                    break
            elapsed = prior_seconds + time.monotonic() - scoring_started
            store.db.execute("UPDATE clock SET seconds=?", [elapsed])
            store.db.commit()
            counts = store.counts()
            completed = counts["completed"]
            attempted = counts["attempted"]
            finished = attempted == requested and counts["server_failed"] == 0
            report = {
                **_progress(store, requested, elapsed),
                "status": (
                    "complete"
                    if completed == requested
                    else "complete_with_unscorable"
                    if finished
                    else "storage_limited"
                    if stopped_for_storage
                    else "deadline_reached"
                    if deadline_reached
                    else "incomplete"
                ),
                "failed": attempted - completed,
                "elapsed_seconds": elapsed + preparation_seconds,
                "frame_preparation_seconds": preparation_seconds,
                "throughput_completed": completed,
                "throughput_elapsed_seconds": elapsed,
                "articles_per_second": completed / elapsed if elapsed else 0,
                "frame_documents": frame_count,
                "frame_records": frame_count,
                "frame_unit": "retained_source_records",
                "selection": (
                    "deterministic SHA256 priority sample of retained source rows"
                    if benchmark
                    else "all retained source rows in source order"
                ),
                "seed": config.seed,
                "row_groups_read": reader.groups_read,
                "contract_sha256": fingerprint,
                "decision_attempts": int(
                    store.db.execute("SELECT attempts FROM clock").fetchone()[0]
                ),
                "unique_scored_inference_units": int(
                    store.db.execute(
                        "SELECT count(*) FROM requests WHERE status='complete'"
                    ).fetchone()[0]
                ),
                "estimated_full_seconds": preparation_seconds
                + frame_count * elapsed / completed
                if completed
                else None,
                "completion_requires_context_policy": counts["context_deferred"] > 0,
            }
            _write_json(
                output / ("benchmark.json" if benchmark else "summary.json"), report
            )
            _write_json(output / "progress.json", report)
            if benchmark:
                _export(store, output)
            if not finished:
                raise RuntimeError(
                    f"Scoring {report['status']}: {completed}/{requested} "
                    "source records "
                    "scored; checkpoints preserved"
                )
    finally:
        store.close()


def benchmark_article_labels(
    input: Annotated[Path, typer.Option(help="Completed compact CPU article index.")],
    output: Annotated[
        Path, typer.Option(help="Resumable benchmark decisions and measured rate.")
    ],
    params: Annotated[
        Path, typer.Option(help="Versioned experiment parameters.")
    ] = Path("params.yaml"),
    source: Annotated[
        Path | None,
        typer.Option(help="Original article Parquet root; overrides the CPU manifest."),
    ] = None,
) -> None:
    """Measure end-to-end scoring on the configured probability sample."""
    asyncio.run(_run(input, output, params, benchmark=True, source=source))


def score_articles(
    input: Annotated[Path, typer.Option(help="Completed compact CPU article index.")],
    output: Annotated[
        Path, typer.Option(help="Resumable document and company decisions.")
    ],
    params: Annotated[
        Path, typer.Option(help="Versioned experiment parameters.")
    ] = Path("params.yaml"),
    source: Annotated[
        Path | None,
        typer.Option(help="Original article Parquet root; overrides the CPU manifest."),
    ] = None,
) -> None:
    """Score every indexed document, preserving checkpoints on interruption."""
    asyncio.run(_run(input, output, params, benchmark=False, source=source))
