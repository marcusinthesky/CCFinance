"""Fit the monthly body-vector probes and report their daily portfolio diagnostics."""

import csv
import warnings
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated

import duckdb
import numpy as np
import typer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

TARGETS = ("reaction", "drift")
MIN_ROWS = 100
MAX_ITER = 10
SEED = 42
FEATURES = 768


def _shift_month(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def training_start(month: date) -> date:
    """Apply the archive's six-month offset to the inclusive last training day."""
    return _shift_month(month - timedelta(days=1), -6) + timedelta(days=1)


def fit_disposition(training_rows: int, test_rows: int, classes: set[int]) -> str:
    """Identify the archive's fitting requirements without stopping later months."""
    if test_rows == 0:
        return "empty_test_month"
    if training_rows < MIN_ROWS:
        return "insufficient_training"
    if len(classes) < 2:
        return "single_class"
    if 1 not in classes:
        return "no_positive_class"
    return "fit"


def fit_lopez_probes(
    sample: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    prediction_start: str = "2021-10-01",
    prediction_end: str = "2024-05-31",
) -> None:
    """Fit both sign classifiers and write predictions and a monthly audit."""
    fit_probes(sample, output, prediction_start, prediction_end)


def fit_probes(
    sample: Path,
    output: Path,
    prediction_start: str = "2021-10-01",
    prediction_end: str = "2024-05-31",
    title_vectors: dict[str, tuple[Path, int]] | None = None,
) -> None:
    """Fit rolling body and optional title probes on the fixed event sample."""
    first = date.fromisoformat(prediction_start)
    last = date.fromisoformat(prediction_end)
    if first.day != 1 or last < first:
        msg = (
            "Prediction start must be the first of a month, on or before prediction end"
        )
        raise ValueError(msg)
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "2"}) as con:
        rows = con.execute(
            """
            SELECT
                id,cik,ticker,session,published_at,captured_at,label_observed_at,title_named,
                   reaction,drift,embedding
            FROM read_parquet(?)
            ORDER BY session,cik,ticker,published_at,captured_at,id
            """,
            [str(sample / "sample.parquet")],
        ).fetchall()
        title_features = {}
        if title_vectors:
            required_ids = {row[0] for row in rows}
            for name, (path, dimensions) in title_vectors.items():
                vectors = (
                    con.read_parquet(str(path / "**/*.parquet"))
                    .project("id, embedding, has_text")
                    .fetchall()
                )
                by_id = {article_id: embedding for article_id, embedding, _ in vectors}
                if (
                    len(vectors) != len(by_id)
                    or set(by_id) != required_ids
                    or not all(has_text for _, _, has_text in vectors)
                ):
                    msg = f"{name} vectors must match the fixed article IDs exactly"
                    raise ValueError(msg)
                matrix = np.asarray([by_id[row[0]] for row in rows], dtype=np.float64)
                if matrix.shape != (len(rows), dimensions) or not np.allclose(
                    np.linalg.norm(matrix, axis=1), 1.0, atol=1e-3
                ):
                    msg = f"Invalid {name} vector coordinates"
                    raise ValueError(msg)
                title_features[name] = matrix
    body = np.asarray([row[10] for row in rows], dtype=np.float64).reshape(-1, FEATURES)
    y = np.sign(
        np.asarray([[row[8], row[9]] for row in rows], dtype=np.float64).reshape(-1, 2)
    ).astype(np.int8)
    sessions = np.asarray([row[3] for row in rows], dtype="datetime64[D]")
    observable = np.asarray([row[6] for row in rows], dtype="datetime64[s]")
    named = np.asarray([row[7] for row in rows], dtype=np.bool_)
    if not np.all(np.isfinite(body)):
        msg = "Nonfinite body embedding coordinates"
        raise ValueError(msg)

    with (
        (output / "predictions.csv").open("w", newline="") as predictions,
        (output / "windows.csv").open("w", newline="") as windows,
    ):
        prediction_writer = csv.writer(predictions)
        prediction_writer.writerow(
            (
                "sample",
                "target",
                "month",
                "id",
                "cik",
                "ticker",
                "session",
                "published_at",
                "captured_at",
                "label_observed_at",
                "realized_return",
                "realized_sign",
                "predicted_sign",
                "positive_probability",
                "training_rows",
            )
        )
        window_writer = csv.writer(windows)
        window_writer.writerow(
            (
                "sample",
                "target",
                "month",
                "training_start",
                "training_end",
                "test_end",
                "last_label_observed_at",
                "training_rows",
                "training_articles",
                "training_securities",
                "training_security_sessions",
                "negative",
                "zero",
                "positive",
                "test_rows",
                "features",
                "solver",
                "max_iter",
                "random_state",
                "disposition",
                "iterations",
                "convergence_warning",
            )
        )
        features = {"body": body, "title_named_body": body, **title_features}
        for cohort, x in features.items():
            selected = (
                named
                if cohort == "title_named_body"
                else np.ones(len(rows), dtype=np.bool_)
            )
            month = first
            while month <= last:
                start = max(date(2021, 1, 1), training_start(month))
                next_month = _shift_month(month, 1)
                # Both returns are known by the training session's close.
                bound = datetime.combine(month, time.min)
                train = np.flatnonzero(
                    selected
                    & (sessions >= np.datetime64(start))
                    & (sessions < np.datetime64(month))
                    & (observable < np.datetime64(bound))
                )
                test = np.flatnonzero(
                    selected
                    & (sessions >= np.datetime64(month))
                    & (sessions < np.datetime64(next_month))
                    & (sessions <= np.datetime64(last))
                )
                for target_index, target in enumerate(TARGETS):
                    labels = y[train, target_index]
                    disposition = fit_disposition(
                        len(train), len(test), set(map(int, labels))
                    )
                    convergence = None
                    iterations = None
                    if disposition == "fit":
                        with warnings.catch_warnings(record=True) as messages:
                            warnings.simplefilter("always", ConvergenceWarning)
                            model = LogisticRegression(
                                max_iter=MAX_ITER,
                                random_state=SEED,
                                solver="lbfgs",
                                n_jobs=1,
                            ).fit(x[train], labels)
                        iterations = int(max(model.n_iter_))
                        convergence = next(
                            (
                                str(item.message)
                                for item in messages
                                if issubclass(item.category, ConvergenceWarning)
                            ),
                            "",
                        )
                        signs = model.predict(x[test])
                        positive_column = int(np.flatnonzero(model.classes_ == 1)[0])
                        probabilities = model.predict_proba(x[test])[:, positive_column]
                        for index, sign, probability in zip(
                            test, signs, probabilities, strict=True
                        ):
                            row = rows[index]
                            prediction_writer.writerow(
                                (
                                    cohort,
                                    target,
                                    month,
                                    *row[:7],
                                    row[8 + target_index],
                                    int(y[index, target_index]),
                                    int(sign),
                                    float(probability),
                                    len(train),
                                )
                            )
                    window_writer.writerow(
                        (
                            cohort,
                            target,
                            month,
                            start,
                            month - timedelta(days=1),
                            min(last, next_month - timedelta(days=1)),
                            max((rows[i][6] for i in train), default=None),
                            len(train),
                            len({rows[i][0] for i in train}),
                            len({rows[i][1:3] for i in train}),
                            len({rows[i][1:4] for i in train}),
                            int(np.sum(labels == -1)),
                            int(np.sum(labels == 0)),
                            int(np.sum(labels == 1)),
                            len(test),
                            x.shape[1],
                            "lbfgs",
                            MAX_ITER,
                            SEED,
                            disposition,
                            iterations,
                            convergence,
                        )
                    )
                month = next_month
