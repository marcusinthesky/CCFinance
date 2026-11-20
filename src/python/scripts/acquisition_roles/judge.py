"""Run the blinded reference or independent fact extraction on the frozen sample."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import duckdb
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

LUNA = "openai-codex:gpt-6-luna"
TERRA = "openai-codex:gpt-6.1-terra"
REFERENCE = """Using only the supplied news, identify a single whole-company acquisition
or bid involving the two listed issuers. Include explicit proposed or failed deals.
Return other for asset purchases, minority stakes or third parties, unclear for
insufficient evidence. Cite verbatim text supporting a directional decision."""
EXTRACT = """Using only the supplied news, write one factual sentence describing what
the focal company did, experienced or proposed. Preserve direction and uncertainty.
Cite verbatim support. Return two null fields when no distinct fact is supported."""


class Direction(BaseModel):
    """Direction supported by the source."""

    direction: Literal["A_buys_B", "B_buys_A", "other", "unclear"]
    quote: str | None


class Fact(BaseModel):
    """Source-grounded statement or abstention."""

    statement: str | None
    quote: str | None


def digest(value: object) -> str:
    """Hash the versioned judgment input."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def evaluate(job: dict, cache: Path) -> dict:
    """Resume a single content-addressed model call."""
    key = digest(job)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (key + ".json")
    if path.exists():
        return json.loads(path.read_text())
    fact = job["role"] == "fact"
    schema = Fact if fact else Direction
    agent = Agent(
        job["model"],
        output_type=schema,
        instructions=job["rubric"],
        model_settings=OpenAIResponsesModelSettings(openai_reasoning_effort="low"),
        retries=2,
    )
    prompt = job["prompt"]

    @agent.output_validator
    def validate(output: Fact | Direction) -> Fact | Direction:
        required = (
            output.statement is not None
            if fact
            else output.direction in ("A_buys_B", "B_buys_A")
        )
        if fact and output.statement is not None and not output.statement.strip():
            raise ModelRetry("Provide a factual sentence or abstain.")
        if (required and not output.quote) or (fact and not required and output.quote):
            raise ModelRetry("Supply the supporting quote with the assertion.")
        if output.quote is not None and (
            not output.quote.strip()
            or not any(output.quote in prompt[field] for field in ("body", "title"))
        ):
            raise ModelRetry("Copy supporting text exactly from the source.")
        return output

    answer = agent.run_sync(json.dumps(prompt)).output
    record = {k: job[k] for k in ("id", "role", "model", "ciks")}
    record.update(answer.model_dump(), key=key)
    if answer.quote:
        field = next(k for k in ("body", "title") if answer.quote in prompt[k])
        start = prompt[field].index(answer.quote)
        record.update(source=field, start=start, stop=start + len(answer.quote))
    with NamedTemporaryFile("w", dir=cache, delete=False) as out:
        json.dump(record, out)
    Path(out.name).replace(path)
    return record


def main() -> None:
    """Run reference or extraction calls for the requested sample."""
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(row)
        for (row,) in duckdb.execute(
            "SELECT to_json(s) FROM read_parquet(?) s", [str(args.sample)]
        ).fetchall()
    ]
    eligible = None
    if args.labels:
        ids = [
            r["id"]
            for r in json.loads(args.labels.read_text())
            if r["role"] == "primary" and r["direction"] in ("A_buys_B", "B_buys_A")
        ]
        ids.sort(
            key=lambda i: hashlib.sha256(("role-comparison-1/" + i).encode()).digest()
        )
        eligible = set(ids[: len(ids) // 2 * 2])
    jobs = []
    for row in rows:
        firms = row["firms"]
        if eligible is None:
            tasks = [("primary", LUNA, firms)]
            if row["audit"]:
                tasks += [("repeat", LUNA, firms[::-1]), ("audit", TERRA, firms)]
        else:
            tasks = [("fact", TERRA, [f]) for f in firms if row["id"] in eligible]
        for role, model, group in tasks:
            prompt = {"title": row["title"], "body": row["body"]}
            prompt.update(
                dict(
                    zip(
                        ("focal",) if role == "fact" else ("A", "B"),
                        [f["name"] for f in group],
                        strict=True,
                    )
                )
            )
            jobs.append(
                {
                    "id": row["id"],
                    "role": role,
                    "model": model,
                    "effort": "low",
                    "ciks": [f["cik"] for f in group],
                    "prompt": prompt,
                    "schema": (
                        Fact if role == "fact" else Direction
                    ).model_json_schema(),
                    "rubric": EXTRACT if role == "fact" else REFERENCE,
                }
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(lambda job: evaluate(job, args.output.parent / "cache"), jobs)
        )
    with NamedTemporaryFile("w", dir=args.output.parent, delete=False) as out:
        json.dump(results, out)
    Path(out.name).replace(args.output)


if __name__ == "__main__":
    main()
