"""Run a frozen English OntoNotes NER pipeline on the micro-benchmark leads."""

import argparse
import hashlib
import json
from pathlib import Path

import stanza
import torch

PACKAGES = {"tokenize": "combined", "mwt": "combined", "ner": "ontonotes_charlm"}
DEPENDENCIES = {
    "forward_charlm": "1billion",
    "backward_charlm": "1billion",
    "pretrain": "fasttextcrawl",
}


def sha256(path: Path) -> str:
    """Return a file digest without loading the whole artifact."""
    with path.open("rb") as resource:
        return hashlib.file_digest(resource, "sha256").hexdigest()


def main() -> None:
    """Verify the frozen resources and save one prediction row per passage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    resources = args.resources / "resources.json"
    if stanza.__version__ != "1.11.0" or sha256(resources) != (
        "e334b4e200aeaa5c1903223de2f3be066f69d3a50a33c70aa1691407628de1ef"
    ):
        raise ValueError("Stanza or its resources manifest differs from the benchmark")
    catalog = json.loads(resources.read_text())["en"]
    checksums = {}
    for processor, package in (PACKAGES | DEPENDENCIES).items():
        model = args.resources / "en" / processor / f"{package}.pt"
        # MD5 here verifies the checksum distributed by the upstream manifest.
        with model.open("rb") as checkpoint:
            checksum = hashlib.file_digest(checkpoint, "md5").hexdigest()
        if checksum != catalog[processor][package]["md5"]:
            raise ValueError(f"Model checksum mismatch for {model}")
        checksums[f"{processor}/{package}"] = sha256(model)
    print(json.dumps({"torch": torch.__version__, "sha256": checksums}), flush=True)
    torch.set_num_threads(4)
    model = stanza.Pipeline(
        lang="en",
        dir=str(args.resources),
        package=None,
        processors=PACKAGES,
        download_method=None,
        use_gpu=False,
    )
    rows = []
    for line in args.input.read_text(encoding="utf-8").split("\n"):
        if not line:
            continue
        article = json.loads(line)
        text = article["text"]
        doc = model(text)
        spans = [
            {
                "start": entity.start_char,
                "end": entity.end_char,
                "text": text[entity.start_char : entity.end_char],
                "type": entity.type,
            }
            for entity in doc.ents
        ]
        rows.append(
            {"id": article["id"], "text_sha256": article["text_sha256"], "spans": spans}
        )
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
