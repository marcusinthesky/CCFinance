"""Restore blinded sentiment and coreference inputs using frozen audit identifiers."""

import csv
import hashlib
import json
from pathlib import Path

import duckdb

WORK = Path(".runtime/corenlp-audit")
RESULT = Path("data/inputs/article-metadata/corenlp-comparison")
META = Path("data/processed/experiments/article-metadata")
FOCUS = Path("data/processed/experiments/company-links")


def write_rows(path: Path, rows: list[dict]) -> None:
    """Write compact machine-readable audit records."""
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def prepare() -> None:
    """Export exact texts locally, plus preselected blind human review cases."""
    for kind in ("sentiment", "coref"):
        (WORK / kind).mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "4"}) as con:
        con.read_parquet(str(META / "confirmation.parquet")).filter(
            "frame='mention'"
        ).create("units")
        con.execute("""CREATE TABLE selected AS
            SELECT id,m.start,m.stop,u.population/u.draws AS weight,u.stratum,m.text,
                   list_position(financial_sentiment,
                                 list_max(financial_sentiment)) AS idx
            FROM 'data/processed/article-metadata/mentions/*.parquet' m
            JOIN units u USING(id,start,stop) WHERE entity_type='company'""")
        labels = json.loads(
            Path("data/processed/article-metadata/schema.json").read_text()
        )["labels"]["financial_sentiment"]
        ref = {}
        for p in (META / "validation-labels/primary").glob("*.json"):
            j = json.loads(p.read_text())
            if j["frame"] == "mention":
                ref[j["id"], j["start"], j["stop"]] = j["label"]["sentiment"]
        con.execute("""CREATE TABLE full_text AS SELECT id,text AS body
            FROM 'data/raw/fine-news/*/eng_Latn/*.parquet'
            SEMI JOIN (SELECT DISTINCT id FROM units) USING(id)""")
        rows = con.sql("""SELECT s.*,b.body FROM selected s JOIN full_text b USING(id)
                        ORDER BY id,start""").fetchall()
        if len(rows) != 400 or len(ref) != 400:
            raise ValueError("Expected 400 paired primary judgments")
        units = []
        human = []
        for i, (key, start, stop, w, stratum, span, idx, body) in enumerate(rows):
            if body[start:stop] != span:
                raise ValueError(f"Marked text mismatch in {key}")
            tag = f"s{i:03d}"
            (WORK / "sentiment" / (tag + ".txt")).write_text(body)
            # The Java library indexes UTF-16 code units.
            begin = len(body[:start].encode("utf-16-le")) // 2
            end = len(body[:stop].encode("utf-16-le")) // 2
            units.append(
                {
                    "tag": tag,
                    "id": key,
                    "start": start,
                    "stop": stop,
                    "begin": begin,
                    "end": end,
                    "weight": w,
                    "stratum": stratum,
                    "gliner": labels[idx - 1],
                    "ref": ref[key, start, stop],
                }
            )
            human.append(
                {
                    "tag": tag,
                    "before": body[max(0, start - 750) : start],
                    "company": span,
                    "after": body[stop : stop + 750],
                    "human_label": "",
                }
            )
        write_rows(WORK / "units.jsonl", units)
        (WORK / "spans.tsv").write_text(
            "".join(f"{r['tag']}\t{r['begin']}\t{r['end']}\n" for r in units)
        )
        human.sort(
            key=lambda r: hashlib.sha256(("human-71:" + r["tag"]).encode()).digest()
        )
        with (WORK / "human-sentiment.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=human[0].keys())
            writer.writeheader()
            writer.writerows(human[:40])
        articles = (
            con.read_parquet(str(FOCUS / "sample/articles.parquet"))
            .filter("split='test'")
            .order("id")
            .fetchall()
        )
        keys = []
        for i, (key, _split, _title, _day, _host, body, truncated) in enumerate(
            articles
        ):
            tag = f"c{i:03d}"
            (WORK / "coref" / (tag + ".txt")).write_text(body)
            keys.append({"tag": tag, "id": key, "truncated": truncated})
        if len(keys) != 183:
            raise ValueError("Expected 183 test articles")
        write_rows(WORK / "keys.jsonl", keys)


if __name__ == "__main__":
    prepare()
