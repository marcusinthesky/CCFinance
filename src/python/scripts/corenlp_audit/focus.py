"""Evaluate a fixed Stanford chain expansion on the seed-43 article split."""

import csv
import json
from collections import defaultdict

import duckdb
import numpy as np
from pipeline.stages.research.experiments.company_links import SECURITY
from prepare import FOCUS, RESULT, WORK, write_rows


def counts(weight: np.ndarray, sample: np.ndarray) -> np.ndarray:
    """Return precision, recall and F1 using article-level paired weights."""
    hits, predicted, subjects = (weight @ sample).T
    return np.stack(
        (hits / predicted, hits / subjects, 2 * hits / (predicted + subjects)), axis=-1
    )


def main() -> None:
    """Count only additional pronoun or nominal heads from single-issuer chains."""
    keys = [json.loads(s) for s in (WORK / "keys.jsonl").read_text().splitlines()]
    tag_id = {r["tag"]: r["id"] for r in keys}
    if set(tag_id) != set((WORK / "coref-completed.txt").read_text().splitlines()):
        raise ValueError("Coreference run is incomplete")
    chains = defaultdict(list)
    for tag, c, kind, a, b, h, j in csv.reader(
        (WORK / "chains.tsv").read_text().splitlines(), delimiter="\t"
    ):
        chains[tag, int(c)].append((kind, int(a), int(b), int(h), int(j)))
    with duckdb.connect(config={"threads": "4"}) as con:
        con.read_parquet(str(FOCUS / "sample/articles.parquet")).filter(
            "split='test'"
        ).create("drawn")
        con.read_parquet("data/processed/issuers/tickers.parquet").create_view(
            "tickers"
        )
        con.execute(SECURITY)
        con.execute("""
            CREATE TABLE gold AS SELECT * FROM (
                SELECT id,unnest(issuers,recursive:=true) FROM
                'data/processed/experiments/company-links/labels/articles.jsonl'
                WHERE judge='primary') WHERE cik IS NOT NULL AND role='subject';
            CREATE TABLE pairs AS SELECT a.id,a.cik,a.n_mentions,a.evidence,
                EXISTS (SELECT 1 FROM gold g WHERE a.id=g.id AND
                (a.cik=g.cik OR security(a.cik,d.day)=security(g.cik,d.day))) AS subject
                FROM 'data/processed/company-links/articles/*.parquet' a
                JOIN drawn d USING(id) WHERE a.link_score>=0.5
                AND a.relevance_substantive>=0 AND a.first_offset_share<=1
        """)
        pairs = con.sql("select * from pairs order by id,cik").fetchall()
        company = defaultdict(list)
        for key, a, b in con.sql("""SELECT id,start,stop
            FROM 'data/processed/company-links/mentions/*.parquet'
            JOIN drawn USING(id)""").fetchall():
            company[key].append((a, b))
        subjects = dict(con.sql("select id,count(*) from gold group by id").fetchall())
    anchors = defaultdict(list)
    for key, cik, _n, evidence, _subject in pairs:
        anchors[key].extend(
            (s["start"], s["stop"], cik) for s in evidence if s["score"] >= 0.5
        )
    additions = defaultdict(dict)
    for (tag, chain), mentions in chains.items():
        key = tag_id[tag]
        names = {
            (a, b, cik)
            for kind, _, _, h, j in mentions
            if kind == "PROPER"
            for a, b, cik in anchors[key]
            if a <= h and j <= b
        }
        issuers = {cik for _, _, cik in names}
        if len(issuers) != 1:
            continue
        cik = issuers.pop()
        for kind, a, b, h, j in mentions:
            if kind not in ("PRONOMINAL", "NOMINAL") or any(
                x < j and h < y for x, y in company[key]
            ):
                continue
            additions[key, cik][h, j] = (tag, chain, a, b, h, j, kind, sorted(names))
    output = []
    review = []
    extra_heads = []
    for key, cik, n, _evidence, subject in pairs:
        gains = list(additions[key, cik].values())
        output.append(
            {
                "id": key,
                "cik": cik,
                "original": n,
                "additional": len(gains),
                "subject": subject,
            }
        )
        for tag, chain, a, b, h, j, kind, names in gains:
            base = {
                "tag": tag,
                "cik": cik,
                "chain": chain,
                "start": a,
                "stop": b,
                "head": h,
                "end": j,
                "kind": kind,
                "anchors": [[x, y] for x, y, _ in names],
            }
            extra_heads.append(base)
            if n < 3 <= n + len(gains):
                body = (WORK / "coref" / (tag + ".txt")).read_text()
                review.append(
                    dict(
                        **base,
                        marked=body[a:b],
                        context=body[max(0, a - 500) : b + 500],
                        names=[body[x:y] for x, y, _ in names],
                    )
                )
    write_rows(WORK / "antecedent-review.jsonl", review)
    write_rows(RESULT / "added-heads.jsonl", extra_heads)
    write_rows(RESULT / "focus-pairs.jsonl", output)
    ids = list(tag_id.values())
    rng = np.random.default_rng(43)
    w = np.vstack(
        (
            np.ones(len(ids)),
            rng.multinomial(len(ids), np.ones(len(ids)) / len(ids), size=2000),
        )
    )
    values = {}
    result = {}
    for name, expanded in (("named", False), ("chains", True)):
        sample = []
        for key in ids:
            called = [
                r
                for r in output
                if r["id"] == key and r["original"] + expanded * r["additional"] >= 3
            ]
            sample.append(
                [sum(r["subject"] for r in called), len(called), subjects.get(key, 0)]
            )
        mat = np.array(sample)
        values[name] = counts(w, mat)
        result[name] = {
            "hits_predicted_reference": mat.sum(axis=0).tolist(),
            "precision_recall_f1": values[name][0].tolist(),
        }
    diff = values["chains"] - values["named"]
    result["paired_difference_ci"] = np.quantile(
        diff[1:], [0.025, 0.975], axis=0
    ).T.tolist()
    result["articles"] = len(keys)
    result["truncated"] = sum(r["truncated"] for r in keys)
    judgments = [
        json.loads(line)
        for line in (RESULT / "terra-antecedents.jsonl").read_text().splitlines()
    ]
    fields = ("tag", "cik", "head", "end")
    expected = sorted(tuple(r[k] for k in fields) for r in review)
    if sorted(tuple(r[k] for k in fields) for r in judgments) != expected:
        raise ValueError("Antecedent judgments must cover every newly eligible head")
    correct_heads = defaultdict(int)
    for r in judgments:
        correct_heads[tag_id[r["tag"]], r["cik"]] += r["verdict"] == "correct"
    verified = [
        r
        for r in output
        if r["original"] < 3 and r["original"] + correct_heads[r["id"], r["cik"]] >= 3
    ]
    result["antecedent_review"] = {
        "heads": len(judgments),
        "correct_heads": sum(correct_heads.values()),
        "confirmed_new_pairs": len(verified),
        "confirmed_new_subjects": sum(r["subject"] for r in verified),
    }
    if result["named"]["hits_predicted_reference"] != [37, 56, 65]:
        raise ValueError("Named-only baseline differs from the published audit")
    (RESULT / "focus.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
