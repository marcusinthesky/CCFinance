"""Measure the production Gemma tokenizer's visible body on frozen issuer pairs."""

import csv
import json
from pathlib import Path

from transformers import AutoTokenizer

PREFIX = "title: none | text: "


def main() -> None:
    """Preserve character bounds for the third linked mention of each issuer."""
    tokenizer = AutoTokenizer.from_pretrained("/model", local_files_only=True)
    with (
        Path("/input/bodies.jsonl").open() as bodies,
        Path("/output/token_visibility.csv").open("w") as output,
    ):
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("id", "cik", "tokens", "visible_body_end", "third_stop"))
        for line in bodies:
            row = json.loads(line)
            text = PREFIX + row["text"]
            length = len(tokenizer(text, truncation=False)["input_ids"])
            encoded = tokenizer(
                text, return_offsets_mapping=True, truncation=True, max_length=2048
            )
            end = max(stop for _, stop in encoded["offset_mapping"]) - len(PREFIX)
            for issuer in row["issuers"]:
                writer.writerow(
                    (row["id"], issuer["cik"], length, end, issuer["third_stop"])
                )


if __name__ == "__main__":
    main()
