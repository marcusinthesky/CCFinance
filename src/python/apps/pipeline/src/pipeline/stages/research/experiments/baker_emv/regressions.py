"""Fit monthly EMV regressions and report tracking estimates."""

import csv
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

import duckdb
import numpy as np
import typer
from numpy.typing import NDArray
from statsmodels.regression.linear_model import OLS
from statsmodels.stats.sandwich_covariance import S_hac_simple

ROOT = Path("data/research/experiments/baker-emv")
HAC_LAGS = 2


class Specification(NamedTuple):
    """A monthly specification identified by its original Table 1 column."""

    column: int
    outcome: str
    predictors: tuple[str, ...]


MODELS = (
    Specification(1, "vix", ("emv",)),
    Specification(2, "vix", ("emv", "emv_lag1", "emv_lag2")),
    Specification(3, "vix", ("emv", "emv_lag1", "emv_lag2", "vix_lag1")),
    Specification(6, "log_vix", ("log_emv",)),
    Specification(7, "realized_volatility", ("emv",)),
    Specification(8, "realized_volatility", ("emv", "realized_volatility_lag1")),
)


class MonthlyFit(NamedTuple):
    """OLS results and inclusion flags on the input monthly calendar."""

    coefficients: NDArray[np.float64]
    standard_errors: NDArray[np.float64]
    pvalues: NDArray[np.float64]
    nobs: int
    r_squared: float
    included: NDArray[np.bool_]
    fitted: NDArray[np.float64]


def fit_monthly(
    observations: Sequence[Sequence[float | None]],
) -> MonthlyFit:
    """Fit OLS and lag-2 Bartlett HAC, retaining calendar distances across gaps."""
    values = np.asarray(observations, dtype=np.float64)
    included = np.isfinite(values).all(axis=1)
    y = values[included, 0]
    x = np.column_stack([np.ones(len(y)), values[included, 1:]])
    nobs, terms = x.shape
    if nobs <= terms or np.linalg.matrix_rank(x) < terms or not np.var(y):
        raise ValueError("Monthly OLS needs a varying outcome and full-rank design")
    fit = OLS(y, x).fit()
    bread = np.asarray(fit.normalized_cov_params)
    # Months without observations have no score, but still occupy a calendar month.
    scores = np.zeros((len(values), terms))
    scores[included] = x * np.asarray(fit.resid)[:, None]
    meat = np.asarray(S_hac_simple(scores, nlags=HAC_LAGS))
    covariance = (nobs / (nobs - terms)) * bread @ meat @ bread
    test = fit.t_test(np.eye(terms), cov_p=covariance, use_t=True)
    fitted = np.full(len(values), np.nan)
    fitted[included] = np.asarray(fit.fittedvalues)
    return MonthlyFit(
        np.asarray(fit.params),
        np.asarray(test.sd),
        np.asarray(test.pvalue),
        nobs,
        float(fit.rsquared),
        included,
        fitted,
    )


def _tracking_figure(
    target: Path, observed: str, label: str, months: Sequence[date]
) -> None:
    ticks = range(0, len(months), 12)
    positions = ",".join(str(tick) for tick in ticks)
    dates = ",".join(months[tick].strftime("%Y-%m") for tick in ticks)
    target.write_text(
        r"""\documentclass{article}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\pagestyle{empty}
\begin{document}
\noindent
\begin{tikzpicture}
\begin{axis}[
  width=11cm,height=7cm,
"""
        + f"  xtick={{{positions}}}, xticklabels={{{dates}}},\n"
        + r"""  xticklabel style={rotate=30,anchor=east},
  ylabel={Volatility (percent)},ymajorgrids,legend pos=north east,
  unbounded coords=jump
]
"""
        + f"\\addplot[blue, thick] table[x=month_number,y={observed}, col sep=comma]"
        "{tracking.csv};\n"
        + f"\\addlegendentry{{Monthly {label}}}\n"
        + f"\\addplot[orange, thick, dashed] table[x=month_number,y=fitted_{observed},"
        " col sep=comma]"
        "{tracking.csv};\n"
        + r"""\addlegendentry{Fitted on EMV}
\end{axis}
\end{tikzpicture}
\end{document}
""",
        encoding="utf-8",
    )


def _table(
    fits: dict[str, dict[int, MonthlyFit]],
) -> str:
    rows = [
        "# Monthly volatility regressions",
        "",
        "The six columns use the monthly specifications from Table 1.",
        "The estimates describe contemporaneous tracking. Parentheses contain",
        "Newey-West standard errors with two calendar lags and a",
        "degrees-of-freedom correction.",
    ]
    labels = {
        "emv": "EMV",
        "emv_lag1": "EMV, lag 1",
        "emv_lag2": "EMV, lag 2",
        "vix_lag1": "VIX, lag 1",
        "log_emv": "Log EMV",
        "realized_volatility_lag1": "Realized volatility, lag 1",
        "intercept": "Intercept",
    }
    outcomes = (
        "VIX",
        "VIX",
        "VIX",
        "Log VIX",
        "Realized volatility",
        "Realized volatility",
    )
    for variant, estimates in fits.items():
        variant_title = {
            "baseline": "Baseline",
            "minimum_days": "Minimum publication days",
        }[variant]
        rows.extend(["", f"## {variant_title}", ""])
        headings = [
            f"({m.column}) {name}" for m, name in zip(MODELS, outcomes, strict=True)
        ]
        rows.append("| Term | " + " | ".join(headings) + " |")
        rows.append("| --- |" + " ---: |" * len(MODELS))
        for key, label in labels.items():
            cells = []
            for model in MODELS:
                terms = ("intercept", *model.predictors)
                cell = ""
                if key in terms:
                    index = terms.index(key)
                    fit = estimates[model.column]
                    coefficient = fit.coefficients[index]
                    error = fit.standard_errors[index]
                    cell = f"{coefficient:.3f} ({error:.3f})"
                cells.append(cell)
            rows.append(f"| {label} | " + " | ".join(cells) + " |")
        for label, cells in (
            ("Observations", [str(estimates[m.column].nobs) for m in MODELS]),
            ("R²", [f"{estimates[m.column].r_squared:.3f}" for m in MODELS]),
        ):
            rows.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"


def report_baker_emv(
    panel: Path = ROOT / "panel", output: Path = ROOT / "report"
) -> None:
    """Write regressions, inclusion flags, coverage and tracking figures."""
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as work, duckdb.connect() as con:
        stage = Path(work)
        stats: dict[str, dict[int, MonthlyFit]] = {}
        results: list[dict[str, object]] = []
        figure_months: list[date] = []
        monthly = str(panel / "monthly_panel.parquet")
        con.execute(
            "CREATE TEMP TABLE monthly_panel AS FROM read_parquet(?)", [monthly]
        )
        variants = ("baseline", "minimum_days")
        with (
            (stage / "model_inclusion.csv").open(
                "w", newline="", encoding="utf-8"
            ) as flags,
            (stage / "tracking.csv").open(
                "w", newline="", encoding="utf-8"
            ) as tracking,
        ):
            flags_writer = csv.writer(flags)
            fields = ("month", "vix", "realized_volatility", "emv")
            flags_writer.writerow(
                ("variant", "month", *(f"column_{m.column}" for m in MODELS))
            )
            tracking_writer = csv.writer(tracking)
            tracking_writer.writerow(
                ("month_number", *fields, "fitted_vix", "fitted_realized_volatility")
            )
            for variant in variants:
                period_rows = con.execute(
                    "SELECT month, vix, realized_volatility, emv FROM monthly_panel "
                    "WHERE variant = ? ORDER BY month",
                    [variant],
                ).fetchall()
                stats[variant] = {}
                for spec in MODELS:
                    formula_columns = ", ".join((spec.outcome, *spec.predictors))
                    values = con.execute(
                        f"SELECT {formula_columns} FROM monthly_panel "  # noqa: S608
                        "WHERE variant = ? ORDER BY month",
                        [variant],
                    ).fetchall()
                    fit = fit_monthly(values)
                    stats[variant][spec.column] = fit
                    for term, estimate, se, pvalue in zip(
                        ("intercept", *spec.predictors),
                        fit.coefficients.tolist(),
                        fit.standard_errors.tolist(),
                        fit.pvalues.tolist(),
                        strict=True,
                    ):
                        results.append(
                            {
                                "variant": variant,
                                "column": spec.column,
                                "outcome": spec.outcome,
                                "term": term,
                                "estimate": estimate,
                                "standard_error": se,
                                "pvalue": pvalue,
                                "observations": fit.nobs,
                                "r_squared": fit.r_squared,
                            }
                        )
                for index, (month, *observed) in enumerate(period_rows):
                    model_fits = stats[variant]
                    flags_writer.writerow(
                        (
                            variant,
                            month,
                            *(
                                bool(model_fits[m.column].included[index])
                                for m in MODELS
                            ),
                        )
                    )
                    if variant == "baseline":
                        figure_months.append(month)
                        tracking_writer.writerow(
                            (
                                index,
                                month,
                                *(
                                    float("nan") if value is None else value
                                    for value in observed
                                ),
                                model_fits[1].fitted[index],
                                model_fits[7].fitted[index],
                            )
                        )
        with (stage / "regressions.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
        (stage / "table.md").write_text(_table(stats), encoding="utf-8")
        con.execute(
            "CREATE TEMP TABLE coverage AS "
            "FROM read_parquet(?) ORDER BY variant, month, host",
            [str(panel / "coverage.parquet")],
        )
        con.execute(
            "COPY coverage TO ? (FORMAT CSV, HEADER)", [str(stage / "coverage.csv")]
        )
        _tracking_figure(stage / "vix.tex", "vix", "VIX", figure_months)
        _tracking_figure(
            stage / "realized_volatility.tex",
            "realized_volatility",
            "realized volatility",
            figure_months,
        )
        for artifact in stage.iterdir():
            os.replace(artifact, output / artifact.name)
    typer.echo(f"Wrote: {output}")
