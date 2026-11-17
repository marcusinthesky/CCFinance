"""Select a reproducible subset of an existing benchmark sample."""

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    """Order articles by a second hash and retain the requested prefix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=500)
    args = parser.parse_args()
    with args.sample.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if not 0 < args.size <= len(rows):
        raise ValueError("Screen size must be positive and no larger than the sample")
    rows.sort(
        key=lambda row: hashlib.sha256(
            ("screen:" + row["article_id"]).encode()
        ).digest()
    )
    with args.output.open("x", encoding="utf-8") as stream:
        for row in rows[: args.size]:
            stream.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
