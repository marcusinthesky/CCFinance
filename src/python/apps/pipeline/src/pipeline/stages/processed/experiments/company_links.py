"""Sample company mentions and adjudicate them with language models.

The evaluation set is fixed independently of the linker. Mentions come from
GLiNER's company mentions, drawn by seeded hash priority within strata of key
frequency and the number of issuers with that alias. Articles are drawn
uniformly for article-level recall. Judges see neutral issuer search results,
never a linker's choice, so the same labels evaluate every linker version. A
share of mentions is judged again by the same model and by an independent
audit model to measure label reliability. Each article falls in a development
or test split by seeded hash: rules are tuned on development labels and
reported on untouched test labels.
"""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal, TextIO, cast

import duckdb
import typer
from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult, ModelRetry, RunContext
from pydantic_ai.exceptions import (
    AgentRunError,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from pipeline.stages.processed.company_links import row_group
from pipeline.stages.processed.issuers import normalize

WORDS = re.compile(r"[A-Za-z][A-Za-z0-9.\-]*")
SPLIT = "CASE WHEN sha256($seed || ':split:' || id) < '8' THEN 'dev' ELSE 'test' END"
STRATA = """
CASE coalesce(matches, 0) WHEN 0 THEN 'none' WHEN 1 THEN 'one' ELSE 'several' END
|| ':' || CASE WHEN frequency >= 1000 THEN 'head'
               WHEN frequency >= 10 THEN 'torso' ELSE 'tail' END
"""


def _context(con: duckdb.DuckDBPyConnection, source: Path, table: str) -> None:
    """Attach title, date, publisher and text from each sampled row group."""
    con.execute(
        "CREATE TABLE texts (id VARCHAR, title VARCHAR, day DATE, host VARCHAR, "
        "text VARCHAR)"
    )
    units = con.sql(f"SELECT DISTINCT unit FROM {table}").fetchall()  # noqa: S608
    for (unit,) in units:
        stem, group = Path(unit).stem.rsplit("--", 1)
        raw = source / (stem.replace("--", "/") + ".parquet")
        first, stop = row_group(con, raw, int(group))
        con.execute(
            f"""INSERT INTO texts
            SELECT id, metadata.title,
                   coalesce(try_cast(left(metadata.publish_date, 10) AS DATE),
                            metadata.warc_date::DATE),
                   metadata.url_hostname, text
            FROM read_parquet($raw, file_row_number = true)
            WHERE file_row_number >= $first AND file_row_number < $stop
              AND id IN (SELECT id FROM {table} WHERE unit = $unit)""",  # noqa: S608
            {"raw": str(raw), "first": first, "stop": stop, "unit": unit},
        )


def sample_links(
    extraction: Annotated[
        Path, typer.Option(help="GLiNER output with mentions/.")
    ] = Path("data/processed/article-metadata"),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    source: Annotated[Path, typer.Option(help="Raw Fine News shards.")] = Path(
        "data/raw/fine-news"
    ),
    per_stratum: Annotated[int, typer.Option(help="Mentions per stratum.")] = 100,
    articles: Annotated[int, typer.Option(help="Articles for recall.")] = 300,
    window: Annotated[int, typer.Option(help="Context characters per side.")] = 750,
    seed: Annotated[int, typer.Option(help="Sampling seed.")] = 42,
    output: Annotated[Path, typer.Option(help="New sample directory.")] = Path(
        "data/processed/experiments/company-links/sample"
    ),
) -> None:
    """Draw stratified company mentions and uniform articles with context."""
    output.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(dir=output.parent) as spill, duckdb.connect() as con:
        con.execute("SET TimeZone = 'UTC'")
        # Bounded memory over ~100M mentions: top-k aggregates, spilling if needed.
        con.execute("SET memory_limit = '4GB'")
        con.execute("SET temp_directory = ?", [spill])
        con.create_function("normalize_name", normalize, ["VARCHAR"], "VARCHAR")
        con.read_parquet(str(extraction / "mentions/*.parquet"), filename=True).filter(
            "entity_type = 'company'"
        ).create_view("mentions")
        con.read_parquet(str(issuers / "aliases.parquet")).create_view("aliases")
        con.execute(
            """CREATE TABLE keys AS
            SELECT text, normalize_name(text) AS key
            FROM (SELECT DISTINCT text FROM mentions)"""
        )
        con.execute(
            f"""CREATE TABLE drawn_mentions AS
            WITH keyed AS (
                SELECT m.id, m.start, k.key
                FROM mentions AS m JOIN keys AS k USING (text)
            ), frequencies AS (
                SELECT key, count(*) AS frequency FROM keyed GROUP BY key
            ), matches AS (
                SELECT key, count(DISTINCT cik) AS matches FROM aliases GROUP BY key
            ), strata AS (
                SELECT id, start, key, {STRATA} AS stratum,
                       sha256($seed || ':' || id || ':' || start) AS priority
                FROM keyed JOIN frequencies USING (key) LEFT JOIN matches USING (key)
            ), drawn AS (
                SELECT stratum, count(*) AS population,
                       min_by({{'id': id, 'start': start, 'key': key}}, priority,
                              $per_stratum) AS rows
                FROM strata GROUP BY stratum
            )
            SELECT stratum, population, unnest(rows, recursive := true) FROM drawn""",  # noqa: S608 - authored strata expression.
            {"seed": str(seed), "per_stratum": per_stratum},
        )
        con.execute(
            f"""CREATE TABLE sampled AS
            SELECT *, {SPLIT} AS split FROM (
                SELECT d.id, d.start, max(m.stop) AS stop,
                       arg_max(m.text, m.stop) AS text, d.key, d.stratum,
                       d.population,
                       any_value(regexp_extract(m.filename, '[^/]+$')) AS unit
                FROM mentions AS m JOIN drawn_mentions AS d USING (id, start)
                GROUP BY d.id, d.start, d.key, d.stratum, d.population
            )""",  # noqa: S608
            {"seed": str(seed)},
        )
        con.execute(
            f"""CREATE TABLE drawn AS
            WITH ids AS (
                SELECT id, any_value(regexp_extract(filename, '[^/]+$')) AS unit
                FROM mentions GROUP BY id
            ), drawn AS (
                SELECT min_by({{'id': id, 'unit': unit}}, sha256($seed || ':' || id),
                              $articles) AS rows
                FROM ids
            )
            SELECT *, {SPLIT} AS split
            FROM (SELECT unnest(rows, recursive := true) FROM drawn)""",  # noqa: S608
            {"seed": str(seed), "articles": articles},
        )
        _context(con, source, "sampled")
        con.execute(
            """COPY (
                SELECT s.* EXCLUDE (unit), count(*) OVER (PARTITION BY stratum)
                       AS sampled, t.title, t.day, t.host,
                       substr(t.text, greatest(1, s.start + 1 - $window),
                              s.start - greatest(0, s.start - $window))
                       || '⟦' || substr(t.text, s.start + 1, s.stop - s.start)
                       || '⟧' || substr(t.text, s.stop + 1, $window) AS excerpt
                FROM sampled AS s JOIN texts AS t USING (id)
            ) TO $target (FORMAT PARQUET)""",
            {"window": window, "target": str(output / "mentions.parquet")},
        )
        con.execute("DROP TABLE texts")
        _context(con, source, "drawn")
        con.execute(
            """COPY (
                SELECT t.id, drawn.split, t.title, t.day, t.host,
                       left(t.text, 12000) AS text,
                       length(t.text) > 12000 AS truncated
                FROM texts AS t JOIN drawn USING (id)
            ) TO $target (FORMAT PARQUET)""",
            {"target": str(output / "articles.parquet")},
        )
    typer.echo(f"Wrote: {output}")


INSTRUCTIONS = """\
You adjudicate company links in financial news for a research dataset.
Universe: issuers listed on a US exchange (NYSE, Nasdaq, NYSE American, Cboe) on
the article date. Companies traded only over the counter (including OTC ADRs)
or only on foreign exchanges, or not yet or no longer listed, are not_listed.
Subsidiaries, divisions and brands count as their listed parent (YouTube ->
Alphabet). Use the search tool to find an issuer's CIK.
The prompt's search results come from the same tool. Search with a name alone
("Alphabet") or a ticker alone ("GOOGL"), not both. Answer "listed_missing"
(articles: give the name, no CIK) only if you are confident the company was
US-listed on that date and neither its name nor its ticker finds it.
- Exchanges named as listing or trading venues count as their operator
  (Nasdaq Inc.); indices and markets as aggregates (S&P 500, Wall Street) are
  not companies.
- News organisations cited as sources count as their owner if it is listed.
Role: "subject" if the text is substantially about the company, "mentioned"
if it appears in passing, "source_or_venue" for a cited source, data provider
or exchange used as a venue."""

Role = Literal["subject", "mentioned", "source_or_venue"]


class MentionLabel(BaseModel):
    """The issuer a marked mention refers to."""

    decision: Literal[
        "listed", "listed_missing", "not_listed", "not_company", "unsure"
    ] = Field(
        description="listed: a US-listed issuer or its subsidiary or brand; "
        "listed_missing: US-listed then, but not found by search; "
        "not_listed: a company that was not US-listed on that date."
    )
    cik: int | None = Field(description="The issuer's CIK when listed.")
    role: Role | None = Field(description="The role of a listed company.")
    rationale: str = Field(max_length=300)


class ArticleIssuer(BaseModel):
    """One US-listed issuer the article mentions."""

    name: str
    cik: int | None = Field(description="Its CIK, or null if search cannot find it.")
    role: Role


class ArticleLabel(BaseModel):
    """Every US-listed issuer an article mentions."""

    issuers: list[ArticleIssuer]


# Judgements are cached by model, judge, prompt and this version of the task.
VERSION = hashlib.sha256(
    json.dumps(
        [
            INSTRUCTIONS,
            MentionLabel.model_json_schema(),
            ArticleLabel.model_json_schema(),
        ],
        sort_keys=True,
    ).encode()
).hexdigest()


@dataclass
class Lookup:
    """Issuer tables and the article date that judgements are checked against."""

    con: duckdb.DuckDBPyConnection
    day: str


LISTED = """
FROM tickers AS t JOIN issuers AS i USING (cik)
WHERE (t.valid_from IS NULL OR t.valid_from <= $day::DATE)
  AND (t.valid_to IS NULL OR $day::DATE <= t.valid_to)
"""


def describe(lookup: Lookup, ciks: list[int]) -> list[str]:
    """Describe issuers listed on the article date, one line each."""
    rows = lookup.con.execute(
        "SELECT cik, any_value(name), string_agg(DISTINCT ticker || ' ' || exchange, "
        f"', ') {LISTED} AND list_contains($ciks, cik) GROUP BY cik ORDER BY cik",
        {"day": lookup.day, "ciks": ciks},
    ).fetchall()
    return [f"CIK {cik}: {name} ({tickers})" for cik, name, tickers in rows]


def search(lookup: Lookup, query: str) -> list[str]:
    """Issuers listed on the article date whose name, alias or ticker matches.

    A name matches when it equals the query, begins with it, or begins it
    ("Microsoft MSFT" finds Microsoft), and any word of the query may be a ticker.
    """
    ciks = lookup.con.execute(
        """SELECT cik FROM aliases
        WHERE key = $key OR starts_with(key, $key || ' ')
           OR starts_with($key, key || ' ')
           OR (source = 'ticker' AND list_contains($words, upper(alias)))
        GROUP BY cik
        ORDER BY min(CASE WHEN key = $key THEN 0 ELSE 1 END), min(length(key)), cik
        LIMIT 10""",
        {"key": normalize(query), "words": [w.upper() for w in WORDS.findall(query)]},
    ).fetchall()
    return describe(lookup, [cik for (cik,) in ciks])


async def search_issuers(context: RunContext[Lookup], query: str) -> list[str]:
    """Find issuers listed on the article date by name, alias or ticker."""
    return search(context.deps, query) or ["No listed issuer."]


def _check(lookup: Lookup, ciks: list[int]) -> None:
    listed = {
        int(line.split(":")[0].removeprefix("CIK ")) for line in describe(lookup, ciks)
    }
    if unknown := sorted(set(ciks) - listed):
        raise ModelRetry(f"Not listed on {lookup.day}: {unknown}. Search again.")


EFFORTS = ("none", "minimal", "low", "medium")


def agents(model: Model | str, effort: str) -> tuple[Agent, Agent]:
    """Build the mention and article adjudicators with validated outputs."""
    if effort not in EFFORTS:
        raise ValueError(f"Effort must be one of {EFFORTS}")
    settings = OpenAIResponsesModelSettings(openai_reasoning_effort=cast(Any, effort))
    common = {
        "deps_type": Lookup,
        "instructions": INSTRUCTIONS,
        "model_settings": settings,
        "tools": [search_issuers],
        "retries": 2,
    }
    mention = Agent(model, output_type=MentionLabel, **common)
    article = Agent(model, output_type=ArticleLabel, **common)

    @mention.output_validator
    def _mention(context: RunContext[Lookup], label: MentionLabel) -> MentionLabel:
        if label.decision == "listed":
            if label.cik is None:
                raise ModelRetry("Give the CIK, or answer listed_missing.")
            _check(context.deps, [label.cik])
        elif label.cik is not None:
            raise ModelRetry("Give a CIK only for listed issuers.")
        return label

    @article.output_validator
    def _article(context: RunContext[Lookup], label: ArticleLabel) -> ArticleLabel:
        _check(context.deps, [i.cik for i in label.issuers if i.cik is not None])
        return label

    return mention, article


@dataclass(frozen=True)
class Judge:
    """A model that labels all articles and mentions, or a share of mentions."""

    name: str
    model: Model | str
    share: float
    articles: bool = False


def _prompts(con: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    rows = con.sql(
        "SELECT id, start, text, day::VARCHAR, host, title, excerpt "
        "FROM sample_mentions ORDER BY id, start"
    ).fetchall()
    for article, start, text, day, host, title, excerpt in rows:
        found = "\n".join(search(Lookup(con, day), text)) or "None."
        prompt = (
            f"Date: {day}. Publisher: {host}. Title: {title}\n"
            f"Excerpt, with the mention marked by ⟦ ⟧:\n{excerpt}\n\n"
            f"Issuer search results for the marked text, unranked:\n{found}\n\n"
            "Which US-listed issuer, if any, does the marked mention refer to?"
        )
        items.append(
            {"kind": "mention", "id": article, "start": start, "day": day}
            | {"prompt": prompt}
        )
    for article, day, host, title, text in con.sql(
        "SELECT id, day::VARCHAR, host, title, text FROM sample_articles ORDER BY id"
    ).fetchall():
        prompt = (
            f"Date: {day}. Publisher: {host}. Title: {title}\n\n{text}\n\n"
            "List every US-listed issuer this article mentions, with its role."
        )
        items.append({"kind": "article", "id": article, "day": day, "prompt": prompt})
    return items


def _digest(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


async def _run(
    agent: Agent, prompt: str, deps: Lookup
) -> AgentRunResult | AgentRunError | None:
    """Run one judgement, retrying transient failures with backoff.

    Rate limits, server errors and dropped connections are retried; if they
    persist the item stays pending for the next run. A judge that keeps failing
    validation, or a request the API rejects, is returned as its error and
    recorded as a missing judgement rather than retried on every run.
    """
    for delay in (0, 30, 120, 600):
        await asyncio.sleep(delay)
        try:
            return await agent.run(prompt, deps=deps)
        except UnexpectedModelBehavior as error:
            return error
        except ModelHTTPError as error:
            if error.status_code != 429 and error.status_code < 500:
                return error
        except ModelAPIError:
            continue
    return None


async def _judge(
    tasks: list[tuple[dict[str, object], Agent]],
    con: duckdb.DuckDBPyConnection,
    concurrency: int,
    cache: Path,
) -> dict[str, dict[str, object]]:
    done: dict[str, dict[str, object]] = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            done[record["key"]] = record
    limit = asyncio.Semaphore(concurrency)

    async def judge(item: dict[str, object], agent: Agent, handle: TextIO) -> None:
        key = str(item["key"])
        if key in done:
            return
        async with limit:
            deps = Lookup(con.cursor(), str(item["day"]))
            result = await _run(agent, str(item["prompt"]), deps)
        if result is None:
            return
        if isinstance(result, AgentRunError):
            record: dict[str, object] = {"key": key, "output": None}
            record["error"] = str(result)[:300]
        else:
            usage = result.usage
            record = {"key": key, "output": result.output.model_dump()}
            record["usage"] = {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
            }
        done[key] = record
        handle.write(json.dumps(record) + "\n")
        handle.flush()

    with cache.open("a") as handle:
        await asyncio.gather(*(judge(item, agent, handle) for item, agent in tasks))
    return done


def adjudicate(
    sample: Path,
    issuers: Path,
    judges: list[Judge],
    effort: str,
    concurrency: int,
    output: Path,
) -> int:
    """Label the sample with each judge; return the judgements still pending."""
    output.mkdir(parents=True, exist_ok=True)
    tasks: list[tuple[dict[str, object], Agent]] = []
    with duckdb.connect() as con:
        for table in ("issuers", "tickers", "aliases"):
            con.read_parquet(str(issuers / f"{table}.parquet")).create(table)
        for table in ("mentions", "articles"):
            con.read_parquet(str(sample / f"{table}.parquet")).create(f"sample_{table}")
        items = _prompts(con)
        for judge in judges:
            name = (
                judge.model if isinstance(judge.model, str) else judge.model.model_name
            )
            mention, article = agents(judge.model, effort)
            for item in items:
                drawn = int(_digest(judge.name, item["prompt"]), 16) % 1000
                if (item["kind"] == "article" and judge.articles) or (
                    item["kind"] == "mention" and drawn < judge.share * 1000
                ):
                    key = _digest(
                        name, effort, judge.name, VERSION, item["kind"], item["prompt"]
                    )
                    agent = mention if item["kind"] == "mention" else article
                    tasks.append((item | {"judge": judge.name, "key": key}, agent))
        done = asyncio.run(_judge(tasks, con, concurrency, output / "cache.jsonl"))
    for kind in ("mention", "article"):
        with (output / f"{kind}s.jsonl").open("w") as handle:
            for item, _ in tasks:
                record = done.get(str(item["key"]))
                if item["kind"] == kind and record and record["output"] is not None:
                    row = {k: item[k] for k in ("id", "start", "judge") if k in item}
                    output_row = cast(dict[str, object], record["output"])
                    handle.write(json.dumps(row | output_row) + "\n")
    return sum(str(item["key"]) not in done for item, _ in tasks)


def adjudicate_links(
    sample: Annotated[Path, typer.Option(help="Sample directory.")] = Path(
        "data/processed/experiments/company-links/sample"
    ),
    issuers: Annotated[Path, typer.Option(help="Prepared issuer tables.")] = Path(
        "data/processed/issuers"
    ),
    model: Annotated[str, typer.Option(help="Primary PydanticAI model.")] = (
        "openai-codex:gpt-6-luna"
    ),
    audit_model: Annotated[str, typer.Option(help="Independent audit model.")] = (
        "openai-codex:gpt-6.1-terra"
    ),
    effort: Annotated[str, typer.Option(help="Reasoning effort, at most medium.")] = (
        "low"
    ),
    repeat: Annotated[float, typer.Option(help="Mention share re-asked.")] = 0.1,
    audit: Annotated[float, typer.Option(help="Mention share audited.")] = 0.2,
    concurrency: Annotated[int, typer.Option(help="Concurrent requests.")] = 4,
    output: Annotated[Path, typer.Option(help="Labels directory.")] = Path(
        "data/processed/experiments/company-links/labels"
    ),
) -> None:
    """Label sampled mentions and articles, reusing cached judgements."""
    judges = [
        Judge("primary", model, 1.0, articles=True),
        Judge("repeat", model, repeat),
        Judge("audit", audit_model, audit),
    ]
    pending = adjudicate(sample, issuers, judges, effort, concurrency, output)
    typer.echo(f"Wrote: {output} ({pending} judgements pending)")
