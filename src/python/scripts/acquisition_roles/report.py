"""Paired acquisition-role estimates against blinded directional judgments."""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


def roles(r: dict) -> tuple | str:
    """Resolve presentation order to canonical buyer and target."""
    if r["direction"] == "A_buys_B":
        return tuple(r["ciks"])
    if r["direction"] == "B_buys_A":
        return tuple(reversed(r["ciks"]))
    return r["direction"]


def decision(reliable: bool, accuracy: float, gain: float, lo: float, hi: float) -> str:
    """Apply the frozen pilot thresholds."""
    if not reliable:
        return "inconclusive"
    if hi < 0.1:
        return "no-go"
    if accuracy >= 0.65 and gain >= 0.1 and lo > 0:
        return "go"
    return "inconclusive"


def main() -> None:
    """Report all conditions on identical eligible blocks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    d = args.directory
    out = args.output
    out.mkdir(exist_ok=True, parents=True)
    facts = json.loads((d / "facts.json").read_text())
    records = json.loads((d / "labels.json").read_text())
    primary = {r["id"]: roles(r) for r in records if r["role"] == "primary"}
    if len(primary) != (8 if args.development else 80):
        raise ValueError("Incomplete primary judgments")
    deals = sorted(
        (i for i in primary if isinstance(primary[i], tuple)),
        key=lambda i: hashlib.sha256(("role-comparison-1/" + i).encode()).digest(),
    )
    audits = {}
    for judge in ("repeat", "audit"):
        comparisons = {r["id"]: roles(r) for r in records if r["role"] == judge}
        if len(comparisons) != (0 if args.development else 20):
            raise ValueError("Incomplete audit")
        audits[judge] = sum(primary[i] == label for i, label in comparisons.items())
    eligible_audit = sum(isinstance(primary[i], tuple) for i in comparisons)
    blocks = list(zip(deals[::2], deals[1::2], strict=False))
    reliable = len(blocks) >= 20 and min(audits.values()) >= 18 and eligible_audit >= 8
    cases = []
    for model in ("open", "qwen", "gemma"):
        vectors = {}
        table = duckdb.read_parquet(str(d / (model + ".parquet")))
        for values in table.fetchall():
            row = dict(zip(table.columns, values, strict=True))
            vectors[row["id"], row["cik"], row["arm"]] = row
        for block, (a, b) in enumerate(blocks):
            for query, doc in ((a, b), (b, a)):
                for side in (0, 1):
                    q = vectors[query, primary[query][side], "query"]
                    arms = ["mentions", "fact"]
                    if model != "qwen":
                        arms += [
                            arm + ("-title" if model == "gemma" else "-instruct")
                            for arm in arms
                        ]
                    for arm in arms:
                        pos, neg = (
                            vectors[doc, primary[doc][j], arm] for j in (side, 1 - side)
                        )
                        missing = pos["vector"] is None or neg["vector"] is None
                        margin = (
                            None
                            if missing
                            else float(
                                np.dot(
                                    q["vector"],
                                    np.subtract(pos["vector"], neg["vector"]),
                                )
                            )
                        )
                        score = (
                            0 if missing else (int(margin > 0) + 0.5 * int(margin == 0))
                        )
                        cases.append(
                            {
                                "block": block,
                                "query": query,
                                "document": doc,
                                "role": ("buyer", "target")[side],
                                "model": model,
                                "arm": arm,
                                "margin": margin,
                                "score": score,
                                "abstention": missing,
                                "truncated": any(x["truncated"] for x in (q, pos, neg)),
                            }
                        )
    stats = {}
    scores = {}
    truncated = {r["block"] for r in cases if r["truncated"]}
    for model, arm in sorted({(r["model"], r["arm"]) for r in cases}):
        rows = [r for r in cases if (r["model"], r["arm"]) == (model, arm)]
        means = np.array(
            [
                np.mean([r["score"] for r in rows if r["block"] == b])
                for b in range(len(blocks))
            ]
        )
        key = model + "/" + arm
        scores[key] = means
        clean = [r["score"] for r in rows if r["block"] not in truncated]
        stats[key] = dict(
            accuracy=float(means.mean()),
            untruncated=float(np.mean(clean)) if clean else None,
            abstaining_comparisons=sum(r["abstention"] for r in rows),
            **{
                role: float(np.mean([r["score"] for r in rows if r["role"] == role]))
                for role in ("buyer", "target")
            },
        )
    diffs = {}
    result = "inconclusive"
    if blocks:
        draws = np.random.default_rng(48).integers(
            len(blocks), size=(10000, len(blocks))
        )
        for key, values in scores.items():
            model, arm = key.split("/")
            bases = {
                model + "/mentions",
                "open/" + arm.split("-")[0],
                model + "/" + arm.split("-")[0],
            }
            for base in sorted(bases - {key}):
                delta = values - scores[base]
                lo, hi = np.quantile(delta[draws].mean(1), [0.025, 0.975])
                diffs[key + " vs " + base] = [float(delta.mean()), float(lo), float(hi)]
        result = decision(
            reliable,
            stats["open/fact"]["accuracy"],
            *diffs["open/fact vs open/mentions"],
        )
    summary = {
        "decision": result,
        "confirmed": len(deals),
        "blocks": len(blocks),
        "unpaired": deals[-1] if len(deals) % 2 else None,
        "agreement": audits,
        "audited_directional": eligible_audit,
        "exclusions": {
            label: list(primary.values()).count(label) for label in ("other", "unclear")
        },
        "conditions": stats,
        "fact_coverage": {
            "supported_outputs": sum(f["statement"] is not None for f in facts),
            "requested": len(facts),
        },
        "differences": diffs,
    }
    (out / "decision.json").write_text(json.dumps(summary, indent=2) + "\n")
    columns = [
        "block",
        "query",
        "document",
        "role",
        "model",
        "arm",
        "margin",
        "score",
        "abstention",
        "truncated",
    ]
    duckdb.from_df(pd.DataFrame(cases, columns=columns)).to_parquet(
        str(out / "comparisons.parquet")
    )
    lines = [r"\begin{tabular}{lrrr}", r"Condition & Accuracy & Buyer & Target \\"]
    for key, r in stats.items():
        lines.append(
            key
            + " & "
            + " & ".join(f"{100 * r[k]:.1f}" for k in ("accuracy", "buyer", "target"))
            + r" \\"
        )
    n_audit = len(comparisons)
    lines.extend(
        [
            r"\midrule",
            rf"\multicolumn{{4}}{{l}}{{Confirmed deals: {len(deals)}/{len(primary)}. "
            rf"Independent pairs: {len(blocks)}.}} \\",
            rf"\multicolumn{{4}}{{l}}{{Agreement: Luna {audits['repeat']}/{n_audit}, "
            rf"Terra {audits['audit']}/{n_audit}.}} \\",
        ]
    )
    contrast = diffs.get("open/fact vs open/mentions")
    if contrast:
        gain, lo, hi = (100 * x for x in contrast)
        lines.append(
            rf"\multicolumn{{4}}{{l}}{{OpenSearch gain: {gain:.1f} pp "
            rf"[{lo:.1f}, {hi:.1f}]. Decision: {result}.}} \\"
        )
    lines.append(r"\end{tabular}")
    (out / "comparison.tex").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
