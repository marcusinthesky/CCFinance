"""Draw reproducible pilot units from usable articles for metadata validation."""

from pathlib import Path
from typing import Annotated

import duckdb
import typer


def sample_metadata_pilot(
    articles: Annotated[Path, typer.Option()],
    extraction: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    seed: Annotated[int, typer.Option()] = 45,
    size: Annotated[int, typer.Option(min=1)] = 30,
) -> None:
    """Sample articles, extracted company mentions and stored windows separately."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        con.execute("SET memory_limit='4GB'")
        con.read_parquet(str(articles)).filter("usable").project("id").create(
            "eligible"
        )
        for name in ("articles", "mentions"):
            con.read_parquet(str(extraction / name / "*.parquet")).create_view(name)
        frames = {
            "article": "SELECT id, 0 AS start, NULL::BIGINT AS stop FROM articles",
            "mention": (
                "SELECT id, start, stop FROM mentions WHERE entity_type = 'company'"
            ),
            "window": "SELECT id, w.start, w.stop FROM articles, unnest(windows) t(w)",
        }
        con.execute(
            "CREATE TABLE sample(frame VARCHAR, id VARCHAR, start BIGINT, stop BIGINT)"
        )
        for frame, query in frames.items():
            con.execute(
                f"""INSERT INTO sample SELECT $frame, id, start, stop FROM ({query})
                JOIN eligible USING (id)
                ORDER BY sha256(concat_ws(':', $seed, $frame, id, start, stop)),
                         id, start, stop LIMIT $size""",  # noqa: S608 - fixed frame queries.
                {"seed": str(seed), "frame": frame, "size": size},
            )
        con.table("sample").write_parquet(str(output))


def _allocation(counts: dict[str, int], size: int, event: bool) -> dict[str, int]:
    """Allocate fixed seats under class capacity with deterministic rounding."""
    total = sum(counts.values())
    if total < size:
        raise ValueError("Frame smaller than requested sample")
    targets = {
        key: size * (count / total + 1 / len(counts)) / 2
        for key, count in counts.items()
    }
    if event and "empty" in counts and len(counts) > 1:
        targets = dict.fromkeys(counts, size / (2 * (len(counts) - 1)))
        targets["empty"] = size / 2
    allocation = dict.fromkeys(counts, 0)
    for _ in range(size):
        key = max(
            (k for k in sorted(counts) if allocation[k] < counts[k]),
            key=lambda k: targets[k] - allocation[k],
        )
        allocation[key] += 1
    return allocation


def sample_metadata_confirmation(
    articles: Annotated[Path, typer.Option()],
    extraction: Annotated[Path, typer.Option()],
    pilot: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    size: Annotated[int, typer.Option(min=1)] = 400,
    seed: Annotated[int, typer.Option()] = 46,
) -> None:
    """Stratify each frame by production prediction and exclude pilot articles."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        con.execute("SET threads=4")
        con.execute("SET memory_limit='4GB'")
        con.read_parquet(str(pilot)).create_view("pilot")
        con.read_parquet(str(articles)).create_view("quality")
        con.execute(
            "CREATE TABLE eligible AS SELECT id FROM quality WHERE usable "
            "AND id NOT IN (SELECT id FROM pilot)"
        )
        for name in ("mentions", "articles"):
            con.read_parquet(str(extraction / name / "*.parquet")).create_view(name)
        frames = {
            "article": "SELECT id, 0 AS start, NULL::BIGINT AS stop, "
            "article_form AS stratum FROM articles",
            "mention": "SELECT id, start, stop, list_position(financial_sentiment, "
            "list_max(financial_sentiment))::VARCHAR AS stratum FROM mentions "
            "WHERE entity_type = 'company'",
            "window": "SELECT id, w.start, w.stop, CASE WHEN list_max(w.event_family) "
            ">= 0.5 THEN list_position(w.event_family,list_max(w.event_family))"
            "::VARCHAR ELSE 'empty' END AS stratum FROM articles, unnest(windows) t(w)",
        }
        con.execute(
            "CREATE TABLE confirmation(frame VARCHAR,id VARCHAR,start BIGINT,"
            "stop BIGINT,stratum VARCHAR,population BIGINT,draws BIGINT,audit BOOLEAN)"
        )
        for frame, query in frames.items():
            con.execute(
                f"""CREATE OR REPLACE TEMP VIEW units AS SELECT id,start,stop,
                coalesce(stratum,'missing') AS stratum FROM ({query})
                JOIN eligible USING (id)"""  # noqa: S608 - fixed frame queries.
            )
            counts = dict(
                con.sql("SELECT stratum,count(*) FROM units GROUP BY 1").fetchall()
            )
            draws = _allocation(counts, size, frame == "window")
            con.execute(
                "CREATE OR REPLACE TEMP TABLE quotas(stratum VARCHAR,n BIGINT,k BIGINT)"
            )
            con.executemany(
                "INSERT INTO quotas VALUES (?,?,?)",
                [(k, counts[k], v) for k, v in draws.items()],
            )
            con.execute(
                """INSERT INTO confirmation WITH ranked AS (
                SELECT *,row_number() OVER (PARTITION BY stratum ORDER BY
                sha256(concat_ws(':',$seed,id,start,stop)),id,start,stop) AS priority
                FROM (SELECT stratum,unnest(arg_min(struct_pack(id:=id,start:=start,
                stop:=stop),sha256(concat_ws(':',$seed,id,start,stop)),$size),
                recursive:=true) FROM units GROUP BY stratum)
                JOIN quotas USING(stratum))
                SELECT $frame,id,start,stop,stratum,n,k,row_number() OVER (
                ORDER BY sha256(concat_ws(':','audit',$seed,id,start,stop)),
                         id,start,stop)
                <= $audit FROM ranked WHERE priority<=k""",
                {"seed": str(seed), "size": size, "frame": frame, "audit": size // 4},
            )
        con.table("confirmation").write_parquet(str(output))
