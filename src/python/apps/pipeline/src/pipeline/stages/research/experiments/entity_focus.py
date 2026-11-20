"""Choose templates on development, then estimate paired held-out gains."""

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import typer

from pipeline.experiments.entity_focus import CANDIDATES

ROOT = Path("data/processed/experiments/entity-focus")
REPORT = Path("data/research/experiments/entity-focus")
MODELS = ("open", "qwen", "gemma")


def measure(vectors: list, refs: list, plain: np.ndarray) -> dict:
    """Match each company's vector against both reference summaries."""
    sims = np.asarray(vectors) @ np.asarray(refs).T
    margins = np.diag(sims) - np.diag(sims[:, ::-1])
    return {
        "both": int(min(margins) > 0),
        "individual": float(np.mean(margins > 0)),
        "margin": float(margins.mean()),
        "own": float(np.diag(sims).mean()),
        "plain": float(np.mean(np.asarray(vectors) @ plain)),
        "a_margin": float(margins[0]),
        "b_margin": float(margins[1]),
    }


def records(split: str) -> tuple[pd.DataFrame, list]:
    """Use the same population of full-length articles for each encoder."""
    refs = json.loads((ROOT / f"{split}-references.json").read_text())
    sample = {
        r["id"]: r
        for r in duckdb.read_parquet(str(ROOT / "sample.parquet"))
        .df()
        .to_dict("records")
    }
    scores = []
    diagnostics = []
    selection = (
        {} if split == "dev" else json.loads((ROOT / "selection.json").read_text())
    )
    for r in refs:
        story = sample[r["id"]]
        blocks = {}
        common = True
        for m in MODELS:
            path = ROOT / f"{split}-{m}" / (r["id"][10:-1] + ".parquet")
            tab = duckdb.read_parquet(str(path))
            rows = [dict(zip(tab.columns, v, strict=True)) for v in tab.fetchall()]
            blocks[m] = rows
            common &= not any(
                x["truncated"]
                for x in rows
                if x["arm"] in CANDIDATES or x["arm"] == "plain"
            )
        diag = {
            "id": r["id"],
            "stratum": f"{story['yr']}/{story['stratum']}",
            "weight": int(story["stratum_total"]),
            "common": common,
            "luna_status": r["luna"]["pair"]["status"],
            "terra_status": r.get("terra", {}).get("pair", {}).get("status"),
        }
        diagnostics.append(diag)
        for m, rows in blocks.items():
            arms = {x["arm"] for x in rows if x["vector"] is not None}
            mat = {
                a: [
                    np.array(
                        next(
                            x["vector"]
                            for x in rows
                            if x["arm"] == a and x["side"] == i
                        )
                    )
                    for i in range(2)
                ]
                for a in arms
            }
            for ref in sorted(
                arms & {"luna_masked", "luna_named", "terra_masked", "terra_named"}
            ):
                for arm in sorted(
                    arms - {"luna_masked", "luna_named", "terra_masked", "terra_named"}
                ):
                    scores.append(
                        diag
                        | {
                            "model": m,
                            "arm": arm,
                            "reference": ref,
                            "selected": arm == selection.get(m),
                        }
                        | measure(mat[arm], mat[ref], mat["plain"][0])
                    )
    return pd.DataFrame(scores), diagnostics


def gain(left: pd.DataFrame, right: pd.DataFrame, alpha: float = 0.05) -> dict:
    """Paired article bootstrap within the ten sampling strata."""
    d = left.merge(
        right[["id", "both"]], on="id", suffixes=("", "_base"), validate="one_to_one"
    ).sort_values("id")
    if not len(d):
        return {"n": 0, "gain": None, "low": None, "high": None}
    delta = d.both - d.both_base
    rng = np.random.default_rng(48)
    draws = np.zeros(10000)
    for _, group in d.assign(delta=delta).groupby("stratum"):
        draws += rng.choice(
            group.delta.to_numpy(), (len(draws), len(group)), replace=True
        ).sum(axis=1)
    lo, hi = np.quantile(draws / len(d), [alpha / 2, 1 - alpha / 2])
    return {
        "n": len(d),
        "gain": float(delta.mean()),
        "low": float(lo),
        "high": float(hi),
        "weighted_gain": float(np.average(delta, weights=d.weight)),
    }


def score_entity_focus(split: str = typer.Option(...)) -> None:
    """Materialize the independent development and confirmation outputs."""
    if split not in ("dev", "test"):
        raise ValueError("Expected dev or test")
    data, diag = records(split)
    directory = ROOT if split == "dev" else REPORT
    directory.mkdir(exist_ok=True, parents=True)
    pd.DataFrame(diag).to_csv(directory / f"{split}-coverage.csv", index=False)
    if data.empty:
        raise ValueError("No distinguishable reference pairs")
    duckdb.from_df(data).to_parquet(str(directory / f"{split}-margins.parquet"))
    mainset = data[data.common & (data.reference == "luna_masked")]
    if split == "dev":
        selection = {}
        for model in MODELS:
            perf = (
                mainset[mainset.model == model]
                .groupby("arm")[["both", "margin"]]
                .mean()
            )
            selection[model] = max(CANDIDATES, key=lambda arm: tuple(perf.loc[arm]))
        (ROOT / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")
        return
    selection = json.loads((ROOT / "selection.json").read_text())
    estimates = []
    qualified = []
    for model in MODELS:
        for ref in ("luna_masked", "terra_masked"):
            frame = data[data.common & (data.reference == ref) & (data.model == model)]
            selected = frame[frame.arm == selection[model]]
            estimates.append(
                {
                    "model": model,
                    "reference": ref,
                    **gain(selected, frame[frame.arm == "header"]),
                }
            )
        luna, terra = estimates[-2:]
        if (
            luna["n"] >= 60
            and terra["n"] >= 20
            and luna["gain"] >= 0.1
            and luna["low"] > 0
            and terra["gain"] > 0
        ):
            qualified.append(model)
    comparisons = {}
    for model in MODELS:
        for other in MODELS:
            if model != other:
                comparisons[f"{model}/{other}"] = gain(
                    mainset[(mainset.model == model) & mainset.selected],
                    mainset[(mainset.model == other) & mainset.selected],
                    0.05 / 3,
                )
    winners = [
        m
        for m in qualified
        if all((comparisons[f"{m}/{o}"]["low"] or 0) > 0 for o in MODELS if o != m)
    ]
    table = []
    for (model, arm, ref), group in data.groupby(["model", "arm", "reference"]):
        for cohort, g in [("native", group), ("full", group[group.common])]:
            if len(g):
                table.append(
                    {
                        "model": model,
                        "arm": arm,
                        "reference": ref,
                        "cohort": cohort,
                        "n": len(g),
                        "correct": int(g.both.sum()),
                        "accuracy": g.both.mean(),
                        "weighted": np.average(g.both, weights=g.weight),
                        "individual": g.individual.mean(),
                        "margin": g.margin.mean(),
                        "cosine_to_article": g.plain.mean(),
                        "cosine_to_summary": g.own.mean(),
                    }
                )
    pd.DataFrame(table).to_csv(REPORT / "comparison.csv", index=False)
    (REPORT / "decision.json").write_text(
        json.dumps(
            {
                "selection": selection,
                "qualifying": qualified,
                "unique_winners": winners,
                "paired": estimates,
                "models": comparisons,
            },
            indent=2,
        )
        + "\n"
    )
