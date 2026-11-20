"""Offline paired comparison of entity readouts on frozen stories and role swaps."""

import csv
import itertools
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from time import perf_counter

import numpy as np
import pyarrow.parquet as pq
import torch
from encode import MODELS, encoder
from safetensors.torch import load_file
from segments import matches, sentences
from templates import render
from transformers import AutoModel

ROOT = Path("/study")
ROLES = (
    ("acquired", "was acquired by", "purchased another business", "was bought"),
    ("lent funds to", "received a loan from", "provided financing", "borrowed money"),
    ("supplied parts to", "received parts from", "supplied goods", "purchased goods"),
    ("sued", "was sued by", "filed a lawsuit", "faced a lawsuit"),
)
NAMES = (("Merro", "Valden"), ("Zelton Group", "Orris Ltd"), ("Kelva", "Tivren"))


def swaps() -> Iterator[tuple[str, dict, tuple[str, str], bool]]:
    """Generate paired stories in which identities exchange roles."""
    for i, ((active, reverse, left, right), names, passive) in enumerate(
        itertools.product(ROLES, NAMES, (False, True))
    ):
        for flip in (False, True):
            a, b = names[::-1] if flip else names
            body = f"{b} {reverse} {a}." if passive else f"{a} {active} {b}."
            firms = [
                {"spans": [{"start": body.index(n), "stop": body.index(n) + len(n)}]}
                for n in (a, b)
            ]
            yield str(i), {"body": body, "firms": firms}, (left, right), passive


@torch.inference_mode()
def main(model: str) -> None:
    """Produce per-story margins and measure elapsed encoder time on CPU."""
    torch.set_num_threads(3)
    tok, limit, native = encoder(Path("/models"), model)
    path = Path("/models") / MODELS[model]
    prefix = "title: none | text: " if model == "gemma" else ""
    heads = []
    if model != "qwen":
        net = AutoModel.from_pretrained(
            path, dtype=torch.bfloat16 if model == "open" else torch.float32
        ).eval()
        for directory in sorted(path.glob("*_Dense")):
            heads.append(load_file(str(directory / "model.safetensors")))

    def forward(text: str, ranges: list | None = None, perturb: bool = False) -> tuple:
        inputs = tok(text, return_tensors="pt", return_offsets_mapping=True)
        offsets = inputs.pop("offset_mapping")[0].tolist()
        if len(offsets) > limit:
            raise ValueError("Eligible input exceeds token limit")
        if ranges is not None:
            for j, (x, y) in enumerate(offsets):
                if (
                    y > len(prefix)
                    and x < y
                    and not any(x < b and a < y for a, b in ranges)
                ):
                    inputs["attention_mask"][0, j] = 0
                    if perturb:
                        inputs["input_ids"][0, j] = 1
        return net(**inputs).last_hidden_state[0].float(), offsets

    def pool(state: tuple, groups: list) -> np.ndarray:
        hidden, offsets = state
        pieces = []
        for group in groups:
            ids = [
                j
                for j, (x, y) in enumerate(offsets)
                if x < y and any(x < b and a < y for a, b in group)
            ]
            if not ids:
                raise ValueError("Missing span after tokenization")
            pieces.append(hidden[ids].mean(0))
        v = torch.stack(pieces).mean(0)
        for weights in heads:
            v = torch.nn.functional.linear(
                v, weights["linear.weight"].float(), weights.get("linear.bias")
            )
        return torch.nn.functional.normalize(v, dim=0).numpy()

    if model != "qwen":
        probe = prefix + "Merro, Inc. bid twice. Merro, Inc. raised its bid."
        hidden, offsets = forward(probe)
        # Include special tokens for native parity.
        if (
            np.dot(pool((hidden, [(0, 1)] * len(offsets)), [[(0, 1)]]), native(probe))
            < 0.999
        ):
            raise ValueError("Native-vector parity failed")
        spans = [
            (probe.index("Merro"), probe.index("Merro") + 11),
            (probe.rindex("Merro"), probe.rindex("Merro") + 11),
        ]
        xs = [[s] for s in spans]
        np.testing.assert_allclose(
            pool(forward(probe, spans), xs),
            pool(forward(probe, spans, True), xs),
            atol=1e-5,
        )

    rows = []

    def evaluate(
        key: str, story: dict, refs: dict, cached: dict, cohort: str, order: bool | None
    ) -> None:
        body = story["body"]
        bounds = sentences(body)
        start = perf_counter()
        state = forward(prefix + body) if model != "qwen" else None
        shared_time = perf_counter() - start
        masks = []
        outputs = {}
        times = {}
        for side, firm in enumerate(story["firms"]):
            spans = sorted({(s["start"], s["stop"]) for s in firm["spans"]})
            selected = [s for s in bounds if matches(s, firm["spans"])]
            masks.append(selected)

            def save(arm: str, fn: Callable) -> None:
                t = perf_counter()
                outputs.setdefault(arm, []).append(fn())
                times[arm] = times.get(arm, 0) + perf_counter() - t

            for arm in ("sentences", "header"):
                if cached:
                    save(arm, lambda arm=arm, side=side: cached[arm, side])
                else:
                    save(
                        arm,
                        lambda arm=arm, firm=firm: native(
                            render(story, firm, model, arm, bounds)[0]
                        ),
                    )
            if model == "qwen":
                header = render(story, firm, model, "header", bounds)[0][
                    : -len(body)
                ].strip()
                save("suffix", lambda header=header: native(body + "\n" + header))
                continue

            def shifted(rs: list) -> list:
                return [(a + len(prefix), b + len(prefix)) for a, b in rs]

            mentions = shifted(spans)
            groups = [[s] for s in mentions]
            save(
                "context_sentences",
                lambda selected=selected: pool(state, [shifted(selected)]),
            )
            save("context_names", lambda groups=groups: pool(state, groups))
            save(
                "masked_names",
                lambda mentions=mentions, groups=groups: pool(
                    forward(prefix + body, mentions), groups
                ),
            )
            chunk = "\n".join(body[a:b] for a, b in selected)
            save(
                "extracted",
                lambda chunk=chunk: pool(
                    forward(prefix + chunk), [[(len(prefix), len(prefix) + len(chunk))]]
                ),
            )
        for judge, target in refs.items():
            for arm, vectors in outputs.items():
                sims = np.array(vectors) @ np.array(target).T
                diff = sims.diagonal() - sims[:, ::-1].diagonal()
                shared = arm.startswith("context_")
                rows.append(
                    {
                        "id": key,
                        "cohort": cohort,
                        "judge": judge,
                        "arm": arm,
                        "model": model,
                        "shared_sentence": masks[0] == masks[1],
                        "reverse_order": order,
                        "correct": int(min(diff) > 0),
                        "margin": float(diff.mean()),
                        "passes": 1
                        if shared
                        else 0
                        if cached and arm in ("header", "sentences")
                        else 2,
                        "seconds": times[arm] + (shared_time if shared else 0),
                    }
                )

    stories = {s["id"]: s for s in pq.read_table(ROOT / "sample.parquet").to_pylist()}
    for split in ("dev", "test"):
        for r in csv.DictReader(
            (
                ROOT / "dev-coverage.csv"
                if split == "dev"
                else Path("/test-coverage.csv")
            ).open()
        ):
            if r["common"].lower() != "true":
                continue
            judges = [j for j in ("luna", "terra") if r[j + "_status"] == "distinct"]
            if not judges:
                continue
            key = r["id"]
            vectors = {
                (x["arm"], x["side"]): x["vector"]
                for x in pq.read_table(
                    ROOT / f"{split}-{model}" / (key[10:-1] + ".parquet")
                ).to_pylist()
            }
            evaluate(
                key,
                stories[key],
                {j: [vectors[j + "_masked", i] for i in (0, 1)] for j in judges},
                vectors,
                split,
                None,
            )
    summaries = {}
    for key, story, roles, passive in swaps():
        if roles not in summaries:
            summaries[roles] = [
                native(prefix + "The focal company " + r + ".") for r in roles
            ]
        evaluate(key, story, {"fixture": summaries[roles]}, {}, "swaps", passive)
    with Path(f"/out/{model}.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1])
