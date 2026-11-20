"""Render and embed each scored issuer using pinned offline checkpoint pipelines."""

import argparse
import json
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from safetensors.torch import load_file
from segments import matches, sentences
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

PREFIX = (
    "Instruct: Retrieve news passages describing a similar event in which "
    "the focal company played a similar role.\nQuery: "
)
MODELS = {
    "open": "opensearch-v1",
    "gemma": "embeddinggemma-300m",
    "qwen": "Qwen3-Embedding-0.6B",
}


def encoder(root: Path, key: str) -> tuple[object, int, Callable]:
    """Load the checkpoint and its published projection."""
    path = root / MODELS[key]
    if key != "open":
        model = SentenceTransformer(
            str(path),
            device="cpu",
            local_files_only=True,
            model_kwargs={"dtype": torch.float32},
        )

        def encode(text: str) -> np.ndarray:
            return model.encode([text], prompt="", normalize_embeddings=True)[0]

        probe = "Focal company: Example\nAn acquisition was announced."
        inputs = model.tokenizer(probe, return_tensors="pt")
        with torch.inference_mode():
            hidden = model[0].auto_model(**inputs).last_hidden_state.float()
            expected = hidden[:, -1] if key == "qwen" else hidden.mean(1)
            if key == "gemma":
                for directory in ("2_Dense", "3_Dense"):
                    weights = load_file(str(path / directory / "model.safetensors"))
                    expected = torch.nn.functional.linear(
                        expected, weights["linear.weight"].float()
                    )
            expected = torch.nn.functional.normalize(expected)[0].numpy()
        if np.dot(expected, encode(probe)) < 0.999:
            raise ValueError(f"{key} reference-vector parity failed")
        return model.tokenizer, model.max_seq_length, encode

    tokenizer = AutoTokenizer.from_pretrained(path)
    backbone = AutoModel.from_pretrained(path, dtype=torch.bfloat16).eval()
    head = load_file(str(path / "2_Dense/model.safetensors"))

    @torch.inference_mode()
    def encode(text: str) -> np.ndarray:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=8192)
        hidden = backbone(**inputs, use_cache=False).last_hidden_state.float().mean(1)
        vector = torch.nn.functional.linear(
            hidden, head["linear.weight"], head["linear.bias"]
        )
        return torch.nn.functional.normalize(vector)[0].numpy()

    return tokenizer, 8192, encode


def render(
    key: str, title: str, header: str, evidence: str, fact: str | None
) -> Iterator[tuple[str, str | None]]:
    """Render document arms and the fixed query."""
    query_prefix = "task: search result | query: " if key == "gemma" else PREFIX
    yield "query", query_prefix + header + evidence
    for name, body in (("mentions", evidence), ("fact", fact)):
        variants = {"": ""}
        if key == "open":
            variants["-instruct"] = PREFIX
        if key == "gemma":
            variants = {
                "": "title: none | text: ",
                "-title": f"title: {title} | text: ",
            }
        for suffix, prefix in variants.items():
            yield name + suffix, None if body is None else prefix + header + body


def main() -> None:
    """Write native normalized vectors with their exact model inputs."""
    p = argparse.ArgumentParser()
    for arg in ("root", "sample", "facts", "output"):
        p.add_argument(arg, type=Path)
    p.add_argument("model", choices=MODELS)
    args = p.parse_args()
    torch.set_num_threads(3)
    tokenizer, limit, encode = encoder(args.root, args.model)
    probes = [
        encode("Focal company: Example\nAn acquisition was announced."),
        encode("Focal company: Example\nAn acquisition was announced."),
    ]
    dim = {"open": 2048, "gemma": 768, "qwen": 1024}[args.model]
    if (
        probes[0].shape != (dim,)
        or not np.allclose(np.linalg.norm(probes[0]), 1, atol=1e-4)
        or not np.allclose(*probes)
    ):
        raise ValueError(
            f"Invalid {args.model} probe, norm={np.linalg.norm(probes[0])}"
        )
    facts = {
        (r["id"], r["ciks"][0]): r["statement"]
        for r in json.loads(args.facts.read_text())
    }
    rows = []
    for story in pq.read_table(args.sample).to_pylist():
        body = story["body"]
        for firm in story["firms"]:
            idx = (story["id"], firm["cik"])
            if idx not in facts:
                continue
            spans = sorted(firm["spans"], key=lambda s: s["start"])
            surface = Counter(
                body[s["start"] : s["stop"]].strip() for s in spans
            ).most_common(1)[0][0]
            evidence = "\n".join(
                body[a:b].strip() for a, b in sentences(body) if matches((a, b), spans)
            )
            for arm, text in render(
                args.model,
                story["title"],
                "Focal company: " + surface + "\n",
                evidence,
                facts[idx],
            ):
                tokens = len(tokenizer(text)["input_ids"]) if text else 0
                rows.append(
                    {
                        "id": idx[0],
                        "cik": idx[1],
                        "model": args.model,
                        "arm": arm,
                        "text": text,
                        "tokens": tokens,
                        "truncated": tokens > limit,
                        "vector": encode(text) if text else None,
                    }
                )
    tmp = args.output.with_suffix(".tmp")
    pq.write_table(
        pa.Table.from_pylist(
            rows,
            schema=pa.schema(
                [
                    ("id", pa.string()),
                    ("cik", pa.int64()),
                    ("model", pa.string()),
                    ("arm", pa.string()),
                    ("text", pa.string()),
                    ("tokens", pa.int64()),
                    ("truncated", pa.bool_()),
                    ("vector", pa.list_(pa.float32())),
                ]
            ),
        ),
        tmp,
    )
    tmp.replace(args.output)


if __name__ == "__main__":
    main()
