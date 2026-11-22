"""Freeze WikiDict ORG lookups and English Wikipedia sitelinks for the test mentions."""

import argparse
import csv
import gzip
import hashlib
from pathlib import Path
from urllib.parse import unquote

import duckdb
from compare import ROOT


def main() -> None:
    """Apply the pinned dictionary to the frozen mentions offline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dictionary", type=Path)
    args = parser.parse_args()
    with args.dictionary.open("rb") as source:
        if (
            hashlib.file_digest(source, "sha256").hexdigest()
            != "0521f7bddbb3f8c2df4b838edcdb027e19943e135107d5dbb88061469d34ddae"
        ):
            raise ValueError("Unexpected Stanford dictionary")
    surfaces = {
        r[0]
        for r in duckdb.sql("""
        SELECT DISTINCT s.text FROM
        'data/processed/experiments/company-links/sample/mentions.parquet' s JOIN
        read_json_auto(
            'data/processed/experiments/company-links/labels/mentions.jsonl') j
        USING(id,start) WHERE s.split='test' AND j.judge='primary'
        AND j.decision<>'unsure'
    """).fetchall()
    }
    matches = {}
    with gzip.open(args.dictionary, "rt", encoding="utf8") as stream:
        for line in stream:
            surface, page, _score = line.rstrip("\n").split("\t")
            if surface in surfaces:
                matches[surface] = page
    with (ROOT / "public-sitelinks.csv").open() as source:
        items = {
            unquote(row["page"].split("/wiki/", 1)[1]).replace(" ", "_"): row["qid"]
            for row in csv.DictReader(source)
        }
    with (ROOT / "wiki-pages.csv").open("w") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["surface", "page", "qid"])
        writer.writerows(
            (s, matches.get(s, ""), items.get(matches.get(s, "").replace(" ", "_"), ""))
            for s in sorted(matches)
        )


if __name__ == "__main__":
    main()
