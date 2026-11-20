"""Encode selected inputs and independent summaries in each model's own space."""

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import torch
from encode import encoder
from segments import sentences
from templates import ARMS, render, visible


def main() -> None:
    """Write a resumable per-article vector shard with token visibility diagnostics."""
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=["open", "qwen", "gemma"])
    parser.add_argument("split", choices=["dev", "test"])
    args = parser.parse_args()
    root = Path("/study")
    directory = root / f"{args.split}-{args.model}"
    directory.mkdir(exist_ok=True)
    refs = {
        r["id"]: r
        for r in json.loads((root / f"{args.split}-references.json").read_text())
    }
    selected = (
        None
        if args.split == "dev"
        else json.loads((root / "selection.json").read_text())[args.model]
    )
    torch.set_num_threads(3)
    tokenizer, limit, encode = encoder(Path("/models"), args.model)
    for story in pq.read_table(root / "sample.parquet").to_pylist():
        key = story["id"]
        if key not in refs:
            continue
        path = directory / (key[10:-1] + ".parquet")
        # DVC invalidates this directory as a unit if any dependency changes.
        if path.exists():
            continue
        reference = refs[key]
        bounds = sentences(story["body"])
        rows = []
        memo = {}

        def vector(text: str, memo: dict = memo) -> list:
            if text not in memo:
                memo[text] = encode(text).tolist()
            return memo[text]

        for side, firm in enumerate(story["firms"]):
            prefix = "title: none | text: " if args.model == "gemma" else ""
            ref = reference["luna"]["summaries"][side]
            qualified = any(
                j in reference and reference[j]["pair"]["status"] == "distinct"
                for j in ("luna", "terra")
            )
            for judge in ("luna", "terra"):
                if (
                    judge not in reference
                    or reference[judge]["pair"]["status"] != "distinct"
                ):
                    continue
                summary = reference[judge]["summaries"][side]
                for kind in ("masked", "named"):
                    text = prefix + summary[kind]
                    rows.append(
                        {
                            "side": side,
                            "arm": judge + "_" + kind,
                            "vector": vector(text),
                            "tokens": len(tokenizer(text)["input_ids"]),
                            "truncated": False,
                            "lost_mentions": 0,
                            "lost_quote": False,
                        }
                    )
            for arm, title in [(a, False) for a in ARMS] + (
                [(selected, True)] if selected and args.model == "gemma" else []
            ):
                text, mapping = render(story, firm, args.model, arm, bounds, title)
                tokens = tokenizer(text, return_offsets_mapping=True)
                n = len(tokens["input_ids"])
                retained = (
                    tokenizer(
                        text,
                        truncation=True,
                        max_length=limit,
                        return_offsets_mapping=True,
                    )
                    if n > limit
                    else tokens
                )
                cutoff = max((b for _, b in retained["offset_mapping"]), default=0)
                needed = qualified and (
                    not selected
                    or arm in ("plain", "name", "header", "sentences", selected)
                )
                lost = (
                    sum(
                        not visible(s["start"], s["stop"], mapping, cutoff)
                        for s in firm["spans"]
                    )
                    if n > limit
                    else 0
                )
                lost_quote = bool(
                    n > limit
                    and ref.get("source") == "body"
                    and not visible(ref["start"], ref["stop"], mapping, cutoff)
                )
                rows.append(
                    {
                        "side": side,
                        "arm": arm + ("_title" if title else ""),
                        "vector": vector(text) if needed else None,
                        "tokens": n,
                        "truncated": n > limit,
                        "lost_mentions": lost,
                        "lost_quote": lost_quote,
                    }
                )
        tmp = path.with_suffix(".tmp")
        pq.write_table(pa.Table.from_pylist(rows), tmp)
        tmp.replace(path)


if __name__ == "__main__":
    main()
