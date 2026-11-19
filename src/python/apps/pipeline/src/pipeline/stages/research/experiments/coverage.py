"""Report staging coverage and quality: tables, figure data and a LaTeX report.

The report audits the article funnel, publication dates, firm-year coverage,
the Pricing Perspective (PP) screen (at least 47 articles in every year from
2018 to 2022), consecutive-year thresholds, publisher composition and
measurement quality. Population counts come from the full corpus; link and
focus accuracy come from the model-adjudicated company-links sample, and the
residual near-duplicate rate from a seeded sample.

Near-duplicates are measured within a few seeded capture months: sampled usable
linked articles are compared with usable articles linked to the same issuer,
published within a short window and captured in the same months, by Jaccard
similarity of five-word shingles. Pairs across sampled months are missed, so
the rate is a lower bound.

Figures are pgfplots definitions reading CSV files beside them, and
``report.tex`` assembles every table and figure for Tectonic.
"""

import csv
import json
import random
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer
from statsmodels.stats.proportion import proportion_confint

type Row = dict[str, Any]
PP_YEARS = (2018, 2022)
PP_SCREEN = 47
MEASURES = ("raw", "usable", "focused")
SURVIVAL = (1, 2, 3, 5, 8, 12, 20, 30, 47, 75, 100, 150, 250, 400, 600, 1000)
LAG_BINS = (0, 1, 2, 3, 5, 7, 14, 30, 60, 90, 180, 365, 730, 1825, 3650)
WORD = re.compile(r"[a-z0-9]+")


def _escape(value: object) -> str:
    text = str(value)
    for char in ("\\", "&", "%", "$", "#", "_", "{", "}"):
        text = text.replace(char, "\\" + char)
    return text


def _number(value: object, digits: int = 0) -> str:
    if value is None:
        return "--"
    if isinstance(value, float) and not value.is_integer():
        return (
            f"{value:,.{digits or 3}f}" if digits or abs(value) < 1 else f"{value:,.1f}"
        )
    return f"{int(value):,}" if isinstance(value, int | float) else _escape(value)


def _share(value: float | None) -> str:
    return "--" if value is None else f"{100 * value:.1f}\\%"


def table(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    align: str,
    groups: str = "",
) -> str:
    """A booktabs tabular from already formatted cells, with optional groups."""
    lines = [rf"\begin{{tabular}}{{{align}}}", r"\toprule"]
    if groups:
        lines.append(groups)
    lines.append(" & ".join(header) + r" \\")
    lines.append(r"\midrule")
    lines += [" & ".join(row) + r" \\" for row in rows]
    return "\n".join([*lines, r"\bottomrule", r"\end{tabular}"]) + "\n"


def _write_csv(
    path: Path, header: Sequence[str], rows: Sequence[Sequence[Any]]
) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _rows(con: duckdb.DuckDBPyConnection, query: str) -> list[Row]:
    result = con.sql(query)
    return [dict(zip(result.columns, row, strict=True)) for row in result.fetchall()]


def funnel(con: duckdb.DuckDBPyConnection) -> list[Row]:
    """Articles by capture year through date checks, deduplication and linking."""
    return _rows(
        con,
        """WITH linked AS (SELECT id, bool_or(focus) AS focused FROM links GROUP BY id)
        SELECT year(a.captured)::INTEGER AS year, count(*) AS articles,
               count(*) FILTER (WHERE a.date_status = 'consistent') AS dated,
               count(*) FILTER (WHERE a.usable) AS usable,
               count(*) FILTER (WHERE a.usable AND l.id IS NOT NULL) AS linked,
               count(*) FILTER (WHERE a.usable AND l.focused) AS focused
        FROM articles AS a LEFT JOIN linked AS l USING (id)
        GROUP BY ALL ORDER BY year""",
    )


def dates(con: duckdb.DuckDBPyConnection) -> Row:
    """Date status by capture year, lag quantiles, sensitivity and publishers."""
    by_year = _rows(
        con,
        """SELECT year(captured)::INTEGER AS year, count(*) AS articles,
               avg((date_status = 'consistent')::INT) AS consistent,
               avg((date_status = 'archival')::INT) AS archival,
               avg((date_status = 'future')::INT) AS future
        FROM articles GROUP BY ALL ORDER BY year""",
    )
    quantiles = con.sql(
        "SELECT quantile_disc(lag_days, [0.5, 0.75, 0.9, 0.95, 0.99]) FROM articles"
    ).fetchall()[0][0]
    sensitivity = _rows(
        con,
        """SELECT unnest([1, 3, 7, 30, 90]) AS max_lag_days,
               unnest([avg((lag_days BETWEEN -1 AND 1)::INT),
                       avg((lag_days BETWEEN -1 AND 3)::INT),
                       avg((lag_days BETWEEN -1 AND 7)::INT),
                       avg((lag_days BETWEEN -1 AND 30)::INT),
                       avg((lag_days BETWEEN -1 AND 90)::INT)]) AS consistent
        FROM articles""",
    )
    publishers = _rows(
        con,
        """SELECT host, count(*) AS articles,
               avg((date_status = 'archival')::INT) AS archival,
               avg((date_status = 'future')::INT) AS future
        FROM articles GROUP BY host HAVING count(*) >= 10000
        ORDER BY archival DESC, host LIMIT 10""",
    )
    cumulative = _rows(
        con,
        f"""SELECT bin, avg((lag_days <= bin)::INT) AS share
        FROM articles, unnest({list(LAG_BINS)}) AS t(bin)
        WHERE lag_days >= -1 GROUP BY bin ORDER BY bin""",  # noqa: S608 - authored constants.
    )
    monthly = _rows(
        con,
        """SELECT strftime(captured, '%Y-%m') AS month,
               count(*) FILTER (WHERE date_status = 'consistent') AS consistent,
               count(*) FILTER (WHERE date_status = 'archival') AS archival,
               count(*) FILTER (WHERE date_status IN ('future', 'missing')) AS other
        FROM articles GROUP BY ALL ORDER BY month""",
    )
    return {
        "by_year": by_year,
        "lag_quantiles": dict(
            zip(("p50", "p75", "p90", "p95", "p99"), quantiles, strict=True)
        ),
        "sensitivity": sensitivity,
        "publishers": publishers,
        "cumulative": cumulative,
        "monthly": monthly,
    }


def _minimum_counts(con: duckdb.DuckDBPyConnection, frame: str) -> list[Row]:
    """Each issuer's weakest PP-window year, by measure, zero-filled."""
    issuers = (
        "SELECT DISTINCT cik FROM roster WHERE cik IS NOT NULL"
        if frame == "roster"
        else "SELECT DISTINCT cik FROM panel"
    )
    return _rows(
        con,
        f"""WITH frame AS ({issuers}),
        grid AS (SELECT f.cik, y.year FROM frame AS f,
                 range({PP_YEARS[0]}, {PP_YEARS[1] + 1}) AS y(year))
        SELECT g.cik, min(coalesce(p.raw, 0)) AS raw,
               min(coalesce(p.usable, 0)) AS usable,
               min(coalesce(p.focused, 0)) AS focused
        FROM grid AS g LEFT JOIN panel AS p USING (cik, year)
        GROUP BY g.cik""",  # noqa: S608 - authored constants.
    )


def screen(con: duckdb.DuckDBPyConnection) -> Row:
    """Firms meeting each threshold in every PP-window year, by frame and measure."""
    frames = {name: _minimum_counts(con, name) for name in ("all", "roster")}
    survival = [
        {"threshold": threshold}
        | {
            f"{name}_{measure}": sum(row[measure] >= threshold for row in rows)
            for name, rows in frames.items()
            for measure in MEASURES
        }
        for threshold in SURVIVAL
    ]
    roster_ciks = {row["cik"] for row in frames["roster"]}
    comparison = {}
    for name, rows in frames.items():
        for measure in MEASURES:
            weakest = sorted(row[measure] for row in rows)
            passing = [row for row in rows if row[measure] >= PP_SCREEN]
            comparison[f"{name}_{measure}"] = {
                "firms": len(rows),
                "passing": len(passing),
                "median_weakest_year": weakest[len(weakest) // 2] if weakest else None,
                "passing_in_roster": sum(row["cik"] in roster_ciks for row in passing),
            }
    statuses = dict(
        con.sql("SELECT status, count(*) FROM roster GROUP BY 1").fetchall()
    )
    return {"survival": survival, "comparison": comparison, "roster": statuses}


def consecutive(
    panel: list[Row], thresholds: Sequence[int], spans: Sequence[int], years: range
) -> list[Row]:
    """Firms with at least t articles in at least n consecutive complete years."""
    series: dict[int, dict[int, Row]] = {}
    for row in panel:
        if row["year"] in years:
            series.setdefault(row["cik"], {})[row["year"]] = row
    grid = []
    for measure in ("usable", "focused"):
        for threshold in thresholds:
            longest = []
            for by_year in series.values():
                run = best = 0
                for year in years:
                    meets = by_year.get(year, {}).get(measure, 0) >= threshold
                    run = run + 1 if meets else 0
                    best = max(best, run)
                longest.append(best)
            grid.append(
                {"measure": measure, "threshold": threshold}
                | {f"years_{span}": sum(n >= span for n in longest) for span in spans}
            )
    return grid


def breakdowns(con: duckdb.DuckDBPyConnection, complete: range) -> Row:
    """Universe coverage by public-float band and by SIC division."""
    years = f"year BETWEEN {complete.start} AND {complete.stop - 1}"

    def summarise(group: str) -> list[Row]:
        return _rows(
            con,
            f"""SELECT {group} AS grp, count(*) AS issuer_years,
                   avg((usable = 0)::INT) AS zero_usable,
                   median(usable) AS median_usable, median(focused) AS median_focused,
                   avg((usable >= {PP_SCREEN})::INT) AS screened
            FROM panel WHERE in_universe AND {years}
            GROUP BY ALL ORDER BY grp NULLS LAST""",  # noqa: S608 - authored constants.
        )

    bins = _rows(
        con,
        f"""WITH banded AS (
            SELECT float_usd, focused, usable,
                   ntile(20) OVER (ORDER BY float_usd) AS bin
            FROM panel WHERE in_universe AND {years} AND float_usd > 0
        )
        SELECT bin, median(float_usd) AS float_usd, median(focused) AS median_focused,
               median(usable) AS median_usable, avg((usable = 0)::INT) AS zero_usable
        FROM banded GROUP BY bin ORDER BY bin""",  # noqa: S608 - authored constants.
    )
    return {
        "size": summarise("coalesce(size_band::VARCHAR, 'none')"),
        "division": summarise("division"),
        "float_bins": bins,
    }


def publishers(con: duckdb.DuckDBPyConnection) -> Row:
    """Publisher shares, concentration and syndication among usable linked articles."""
    hosts = _rows(
        con,
        """SELECT a.host, count(DISTINCT l.id) AS articles,
               count(DISTINCT l.id) FILTER (WHERE l.focus) AS focused
        FROM links AS l JOIN articles AS a USING (id) WHERE a.usable
        GROUP BY a.host ORDER BY articles DESC, a.host""",
    )
    total = sum(row["articles"] for row in hosts) or 1
    focused = sorted(row["focused"] for row in hosts)
    running, lorenz = 0, [(0.0, 0.0)]
    for index, value in enumerate(focused, start=1):
        running += value
        lorenz.append((index / len(focused), running / (sum(focused) or 1)))
    totals = con.sql(
        """SELECT avg((a.article_form = 'press release')::INT),
                  avg(l.self_publisher::INT), avg(a.copies), avg((a.copies > 1)::INT)
        FROM links AS l JOIN articles AS a USING (id) WHERE a.usable"""
    ).fetchall()[0]
    per_issuer = con.sql(
        "SELECT median(publishers) FROM panel WHERE in_universe AND usable > 0"
    ).fetchall()[0][0]
    return {
        "publishers": len(hosts),
        "top": [row | {"share": row["articles"] / total} for row in hosts[:10]],
        "hhi": sum((row["articles"] / total) ** 2 for row in hosts),
        "lorenz": lorenz,
        "press_release_share": totals[0],
        "self_published_share": totals[1],
        "mean_copies": totals[2],
        "syndicated_share": totals[3],
        "median_publishers_per_issuer_year": per_issuer,
    }


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = WORD.findall(text[:3000].lower())
    return {tuple(words[i : i + 5]) for i in range(max(1, len(words) - 4))}


def near_duplicates(con: duckdb.DuckDBPyConnection, source: Path, settings: Row) -> Row:
    """Share of sampled usable linked articles with a same-issuer near-duplicate."""
    months = sorted(
        month
        for (month,) in con.sql(
            "SELECT DISTINCT strftime(captured, '%Y-%m') FROM articles "
            "WHERE year(captured) BETWEEN 2017 AND 2025"
        ).fetchall()
    )
    count = min(settings["months"], len(months))
    sampler = random.Random(settings["seed"])  # noqa: S311 - seeded sample, not security.
    chosen = sorted(sampler.sample(months, count))
    con.execute(
        """CREATE TEMP TABLE pool AS
        SELECT l.id, l.cik, a.published FROM links AS l JOIN articles AS a USING (id)
        WHERE a.usable AND list_contains($months, strftime(a.captured, '%Y-%m'))""",
        {"months": chosen},
    )
    con.execute(
        "CREATE TEMP TABLE drawn AS SELECT * FROM pool ORDER BY hash(id || $seed) "
        "LIMIT $n",
        {"seed": str(settings["seed"]), "n": settings["articles"]},
    )
    pairs = con.execute(
        """SELECT d.id, p.id AS other FROM drawn AS d JOIN pool AS p
          ON p.cik = d.cik AND p.id <> d.id
         AND abs(date_diff('day', p.published, d.published)) <= $window
        QUALIFY row_number() OVER (PARTITION BY d.id ORDER BY
            abs(date_diff('day', p.published, d.published)), p.id) <= $cap""",
        {"window": settings["window_days"], "cap": settings["max_candidates"]},
    ).fetchall()
    needed = {article for pair in pairs for article in pair}
    needed |= {row[0] for row in con.sql("SELECT id FROM drawn").fetchall()}
    files = [
        str(path) for month in chosen for path in (source / month).rglob("*.parquet")
    ]
    texts = dict(
        con.execute(
            "SELECT id, text FROM read_parquet($files) WHERE list_contains($ids, id)",
            {"files": files, "ids": sorted(needed)},
        ).fetchall()
    )
    shingles = {article: _shingles(text) for article, text in texts.items()}
    flagged: set[str] = set()
    for article, other in pairs:
        a, b = shingles.get(article, set()), shingles.get(other, set())
        if a and b and len(a & b) / len(a | b) >= settings["jaccard"]:
            flagged.add(article)
    sampled = con.sql("SELECT count(*) FROM drawn").fetchall()[0][0]
    low, high = (
        proportion_confint(len(flagged), sampled, method="wilson")
        if sampled
        else (None, None)
    )
    return {
        "months": chosen,
        "sampled": sampled,
        "compared_pairs": len(pairs),
        "with_near_duplicate": len(flagged),
        "rate": len(flagged) / sampled if sampled else None,
        "ci95_low": low,
        "ci95_high": high,
    }


AXIS = "width=0.92\\linewidth, height=6.2cm, grid=major, legend cell align=left"


def _figure(name: str, axis: str, plots: Sequence[str]) -> str:
    """A pgfplots axis whose plots read figures/<name>.csv."""
    lines = [r"\begin{tikzpicture}", rf"\begin{{axis}}[{AXIS}, {axis}]"]
    lines += list(plots)
    return "\n".join([*lines, r"\end{axis}", r"\end{tikzpicture}"]) + "\n"


def _plot(
    name: str, x: str, y: str, legend: str, style: str = "", suffix: str = ""
) -> str:
    options = f"[{style}]" if style else ""
    source = rf"table[x={x}, y={y}, col sep=comma] {{figures/{name}.csv}}"
    return (
        rf"\addplot+{options} {source}{suffix};"
        + "\n"
        + rf"\addlegendentry{{{legend}}}"
    )


def figures(output: Path, data: Row, focus_curve: Path) -> dict[str, str]:
    """Write figure CSVs and return their pgfplots definitions."""
    folder = output / "figures"
    folder.mkdir(exist_ok=True)
    monthly = data["dates"]["monthly"]
    _write_csv(
        folder / "volume.csv",
        ["x", "consistent", "archival", "other"],
        [
            [
                int(row["month"][:4]) + (int(row["month"][5:]) - 1) / 12,
                row["consistent"] / 1e3,
                row["archival"] / 1e3,
                row["other"] / 1e3,
            ]
            for row in monthly
        ],
    )
    _write_csv(
        folder / "lag.csv",
        ["lag", "share"],
        [[row["bin"] + 1, row["share"]] for row in data["dates"]["cumulative"]],
    )
    _write_csv(
        folder / "ccdf.csv",
        ["threshold", "usable", "focused"],
        [[row["threshold"], row["usable"], row["focused"]] for row in data["ccdf"]],
    )
    survival = data["screen"]["survival"]
    _write_csv(
        folder / "survival.csv", list(survival[0]), [list(r.values()) for r in survival]
    )
    bins = data["breakdowns"]["float_bins"]
    _write_csv(
        folder / "size.csv",
        ["float", "focused", "usable", "zero"],
        [
            [
                row["float_usd"] / 1e6,
                row["median_focused"],
                row["median_usable"],
                row["zero_usable"],
            ]
            for row in bins
        ],
    )
    _write_csv(
        folder / "lorenz.csv", ["publishers", "articles"], data["publishers"]["lorenz"]
    )
    with focus_curve.open(newline="") as handle:
        curve = [row for row in csv.DictReader(handle) if row["rule"] == "min_mentions"]
    for split in ("dev", "test"):
        _write_csv(
            folder / f"focus_{split}.csv",
            ["mentions", "precision", "recall"],
            [
                [row["value"], row["precision"], row["recall"]]
                for row in curve
                if row["split"] == split and row["precision"]
            ],
        )
    log_axes = "xmode=log, ymode=log, unbounded coords=discard"
    return {
        "volume": _figure(
            "volume",
            "stack plots=y, area style, xlabel={Capture month}, "
            "ylabel={Articles (thousands)}, "
            "xticklabel style={/pgf/number format/1000 sep={}}, "
            "legend pos=north east, enlarge x limits=false",
            [
                _plot(
                    "volume",
                    "x",
                    "consistent",
                    "Consistent date",
                    "draw=none",
                    r" \closedcycle",
                ),
                _plot(
                    "volume",
                    "x",
                    "archival",
                    "Archival date",
                    "draw=none",
                    r" \closedcycle",
                ),
                _plot(
                    "volume",
                    "x",
                    "other",
                    "Future or missing",
                    "draw=none",
                    r" \closedcycle",
                ),
            ],
        ),
        "lag": _figure(
            "lag",
            "xmode=log, xlabel={Capture lag in days, plus one}, "
            "ylabel={Cumulative share}, legend pos=south east",
            [
                _plot("lag", "lag", "share", "Articles, lag of at least $-1$ day"),
                r"\draw[dashed] (axis cs:8,0) -- (axis cs:8,1);",
            ],
        ),
        "ccdf": _figure(
            "ccdf",
            f"{log_axes}, xlabel={{Articles in the issuer-year, at least}}, "
            "ylabel={Share of issuer-years}, legend pos=south west",
            [
                _plot("ccdf", "threshold", "usable", "Usable"),
                _plot("ccdf", "threshold", "focused", "Focused"),
                rf"\draw[dashed] (axis cs:{PP_SCREEN},1e-4) -- "
                rf"(axis cs:{PP_SCREEN},1);",
            ],
        ),
        "survival": _figure(
            "survival",
            f"{log_axes}, xlabel={{Articles in every year 2018--2022, at least}}, "
            "ylabel={Issuers}, legend columns=3, "
            "legend style={at={(0.5,-0.22)}, anchor=north}",
            [
                _plot("survival", "threshold", f"all_{measure}", f"Listed, {measure}")
                for measure in MEASURES
            ]
            + [
                _plot(
                    "survival",
                    "threshold",
                    f"roster_{measure}",
                    f"PP roster, {measure}",
                    "dashed",
                )
                for measure in MEASURES
            ]
            + [rf"\draw[dotted] (axis cs:{PP_SCREEN},1) -- (axis cs:{PP_SCREEN},1e4);"],
        ),
        "size": _figure(
            "size",
            f"{log_axes}, xlabel={{Public float, US\\$ millions (bin median)}}, "
            "ylabel={Median articles per issuer-year}, legend pos=north west",
            [
                _plot("size", "float", "usable", "Usable"),
                _plot("size", "float", "focused", "Focused"),
            ],
        ),
        "lorenz": _figure(
            "lorenz",
            "xlabel={Share of publishers}, ylabel={Share of focused articles}, "
            "legend pos=north west, xmin=0, xmax=1, ymin=0, ymax=1",
            [
                _plot(
                    "lorenz",
                    "publishers",
                    "articles",
                    "Publishers by focused articles",
                    "mark=none",
                ),
                r"\addplot[dashed, domain=0:1] {x};",
            ],
        ),
        "focus": _figure(
            "focus",
            "xlabel={Recall}, ylabel={Precision}, xmin=0, xmax=1, ymin=0, ymax=1, "
            "legend pos=south west, nodes near coords, point meta=explicit symbolic",
            [
                r"\addplot+ table[x=recall, y=precision, meta=mentions, "
                rf"col sep=comma] {{figures/focus_{split}.csv}};"
                "\n" + rf"\addlegendentry{{{name}, at least $k$ mentions}}"
                for split, name in (("dev", "Development"), ("test", "Test"))
            ],
        ),
    }


def _estimate(value: Row | None) -> list[str]:
    if not value or value.get("estimate") is None:
        return ["--", "--", "0"]
    interval = f"[{value['ci95_low']:.3f}, {value['ci95_high']:.3f}]"
    return [f"{value['estimate']:.3f}", interval, _number(value["n"])]


def tables(data: Row, quality: Row) -> dict[str, str]:
    """LaTeX tables for every report section."""
    rows = data["funnel"]
    total = {key: sum(row[key] for row in rows) for key in rows[0] if key != "year"}
    keys = ("articles", "dated", "usable", "linked", "focused")
    funnel_rows = [[str(row["year"]), *(_number(row[k]) for k in keys)] for row in rows]
    funnel_rows.append(["Total", *(_number(total[k]) for k in keys)])
    dated = data["dates"]
    comparison = data["screen"]["comparison"]
    labels = {"all": "Listed issuers", "roster": "PP roster"}
    screen_rows = [
        [
            labels[frame],
            measure,
            _number(entry["firms"]),
            _number(entry["passing"]),
            _number(entry["median_weakest_year"]),
            _number(entry["passing_in_roster"]) if frame == "all" else "--",
        ]
        for key, entry in comparison.items()
        for frame, measure in [key.split("_", 1)]
    ]
    spans = [key for key in data["consecutive"][0] if key.startswith("years_")]
    group_header = ["Issuer-years", "Zero usable", "Median usable", "Median focused"]
    group_header.append(rf"$\geq {PP_SCREEN}$ usable")

    def group_rows(entries: list[Row]) -> list[list[str]]:
        return [
            [
                _escape(row["grp"]),
                _number(row["issuer_years"]),
                _share(row["zero_usable"]),
                _number(row["median_usable"], 1),
                _number(row["median_focused"], 1),
                _share(row["screened"]),
            ]
            for row in entries
        ]

    publisher = data["publishers"]
    near = data["near_duplicates"]
    near_cell = (
        ["--", "--", "0"]
        if near["rate"] is None
        else [
            f"{near['rate']:.3f}",
            f"[{near['ci95_low']:.3f}, {near['ci95_high']:.3f}]",
            _number(near["sampled"]),
        ]
    )
    links, focus = quality["links"], quality["focus"]
    status = data["status_shares"]
    quality_rows = [
        [
            "Link precision, pooled",
            *_estimate(links["pooled"]["estimates"]["link_precision"]),
        ],
        [
            "Link precision, test",
            *_estimate(links["test"]["estimates"]["link_precision"]),
        ],
        ["Mention recall, pooled", *_estimate(links["pooled"]["estimates"]["recall"])],
        [
            "Article recall, company-focused, pooled",
            *_estimate(links["pooled"]["estimates"]["article_recall"]),
        ],
        ["Focused precision, test", *_estimate(focus["test"]["precision"])],
        ["Focused recall, test", *_estimate(focus["test"]["recall"])],
        ["Same-issuer near-duplicate rate", *near_cell],
        [
            "Archival date share",
            f"{status['archival']:.3f}",
            "",
            _number(status["articles"]),
        ],
        [
            "Future date share",
            f"{status['future']:.3f}",
            "",
            _number(status["articles"]),
        ],
    ]
    survival_rows = [
        [str(row["threshold"]), *(_number(row[key]) for key in list(row)[1:])]
        for row in data["screen"]["survival"]
        if row["threshold"] in (1, 12, PP_SCREEN, 100, 250)
    ]
    return {
        "funnel": table(
            ["Capture year", "Articles", "Dated", "Usable", "Linked", "Focused"],
            funnel_rows,
            "lrrrrr",
        ),
        "dates": table(
            ["Capture year", "Articles", "Consistent", "Archival", "Future"],
            [
                [
                    str(r["year"]),
                    _number(r["articles"]),
                    _share(r["consistent"]),
                    _share(r["archival"]),
                    _share(r["future"]),
                ]
                for r in dated["by_year"]
            ],
            "lrrrr",
        ),
        "lag": table(
            ["Maximum lag (days)", "Consistent share"],
            [
                [str(r["max_lag_days"]), _share(r["consistent"])]
                for r in dated["sensitivity"]
            ],
            "rr",
        ),
        "archival_publishers": table(
            ["Publisher", "Articles", "Archival", "Future"],
            [
                [
                    _escape(r["host"]),
                    _number(r["articles"]),
                    _share(r["archival"]),
                    _share(r["future"]),
                ]
                for r in dated["publishers"]
            ],
            "lrrr",
        ),
        "screen": table(
            [
                "Frame",
                "Measure",
                "Issuers",
                rf"$\geq {PP_SCREEN}$ every year",
                "Median weakest year",
                "Of which in roster",
            ],
            screen_rows,
            "llrrrr",
        ),
        "survival": table(
            [
                "At least",
                *(
                    k.split("_")[1].capitalize()
                    for k in list(data["screen"]["survival"][0])[1:]
                ),
            ],
            survival_rows,
            "r" * 7,
            r" & \multicolumn{3}{c}{Listed issuers} & \multicolumn{3}{c}{PP roster} \\"
            "\n" + r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
        ),
        "consecutive": table(
            ["Measure", "At least", *(f"{k.split('_')[1]}+ years" for k in spans)],
            [
                [
                    row["measure"],
                    str(row["threshold"]),
                    *(_number(row[k]) for k in spans),
                ]
                for row in data["consecutive"]
            ],
            "lr" + "r" * len(spans),
        ),
        "size": table(
            ["Float band", *group_header],
            group_rows(data["breakdowns"]["size"]),
            "lrrrrr",
        ),
        "division": table(
            ["SIC division", *group_header],
            group_rows(data["breakdowns"]["division"]),
            "lrrrrr",
        ),
        "publishers": table(
            ["Publisher", "Usable linked", "Share", "Focused"],
            [
                [
                    _escape(r["host"]),
                    _number(r["articles"]),
                    _share(r["share"]),
                    _number(r["focused"]),
                ]
                for r in publisher["top"]
            ],
            "lrrr",
        ),
        "quality": table(
            ["Measure", "Estimate", r"95\% CI", "$n$"], quality_rows, "lrrr"
        ),
    }


def _float(kind: str, name: str, caption: str) -> str:
    """A table or figure float that inputs a generated file."""
    folder = "tables" if kind == "table" else "figures"
    size = r"\small" if kind == "table" else ""
    return "\n".join(
        [
            rf"\begin{{{kind}}}[!htbp]\centering{size}",
            rf"\input{{{folder}/{name}.tex}}",
            rf"\caption{{{caption}}}",
            rf"\end{{{kind}}}",
        ]
    )


def sections() -> str:
    """Report sections, each starting a page, with their prose and floats."""
    parts = [
        (
            "Article funnel",
            r"Articles by capture year. \emph{Dated} articles were captured within "
            r"the maximum lag of their publication date; \emph{usable} articles are "
            r"dated and canonical; \emph{linked} and \emph{focused} articles carry at "
            "least one issuer link, or one link meeting the company-focus rule.",
            [
                _float("table", "funnel", "Article funnel."),
                _float("figure", "volume", "Monthly captures by date status."),
            ],
        ),
        (
            "Publication dates",
            "",
            [
                _float("table", "dates", "Date status by capture year."),
                _float("table", "lag", "Consistent share by maximum lag."),
                _float(
                    "table",
                    "archival_publishers",
                    "Publishers with the highest archival shares "
                    "(at least 10,000 articles).",
                ),
                _float(
                    "figure",
                    "lag",
                    "Cumulative capture lag; the dashed line is the maximum lag.",
                ),
            ],
        ),
        (
            "Firm-year coverage",
            "Issuer-years in the universe over complete years, by public-float "
            "band (1 is smallest) and by SIC division.",
            [
                _float("table", "size", "Coverage by public-float band."),
                _float("table", "division", "Coverage by SIC division."),
                _float(
                    "figure",
                    "ccdf",
                    "Share of universe issuer-years with at least a given number "
                    "of articles.",
                ),
                _float(
                    "figure", "size", "Median articles per issuer-year by public float."
                ),
            ],
        ),
        (
            "Pricing Perspective screen",
            f"The Pricing Perspective frame keeps firms with at least {PP_SCREEN} "
            r"raw articles in every year from 2018 to 2022. Here \emph{raw} counts "
            "every linked article by its linker date, so it is closest to that "
            "screen.",
            [
                _float("table", "screen", "Issuers passing the screen."),
                _float(
                    "table",
                    "survival",
                    "Issuers with at least a given number of articles in every "
                    "year 2018--2022.",
                ),
                _float(
                    "figure",
                    "survival",
                    "Issuers meeting each threshold in every year 2018--2022.",
                ),
            ],
        ),
        (
            "Consecutive-year thresholds",
            "",
            [
                _float(
                    "table",
                    "consecutive",
                    "Issuers with at least a given number of articles in at least "
                    "$n$ consecutive complete years.",
                )
            ],
        ),
        (
            "Publishers",
            "",
            [
                _float(
                    "table",
                    "publishers",
                    "Largest publishers of usable linked articles.",
                ),
                _float(
                    "figure",
                    "lorenz",
                    "Concentration of focused articles across publishers.",
                ),
            ],
        ),
        (
            "Measurement quality",
            "Link and focus estimates come from model-adjudicated samples (seed 43), "
            "not human labels. The near-duplicate rate is a lower bound from seeded "
            "capture months.",
            [
                _float("table", "quality", "Measurement quality."),
                _float(
                    "figure",
                    "focus",
                    "Company-focus precision and recall by minimum mentions.",
                ),
            ],
        ),
    ]
    return "\n\\clearpage\n".join(
        "\n".join([rf"\section{{{title}}}", prose, *floats])
        for title, prose, floats in parts
    )


def report_tex(headline: str) -> str:
    """The standalone report document."""
    preamble = "\n".join(
        [
            r"\documentclass[10pt]{article}",
            r"\usepackage[margin=2cm]{geometry}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{lmodern}",
            r"\usepackage{booktabs}",
            r"\usepackage{pgfplots}",
            r"\pgfplotsset{compat=1.18}",
            r"\title{Staging coverage audit}",
            r"\author{}",
            r"\date{}",
            r"\begin{document}",
            r"\maketitle",
        ]
    )
    return f"{preamble}\n{headline}\n{sections()}\n\\end{{document}}\n"


def _ccdf(panel: list[Row], years: range) -> list[Row]:
    members = [r for r in panel if r["in_universe"] and r["year"] in years]
    return [
        {"threshold": threshold}
        | {
            measure: sum(r[measure] >= threshold for r in members) / (len(members) or 1)
            for measure in ("usable", "focused")
        }
        for threshold in SURVIVAL
    ]


def _integers(text: str) -> list[int]:
    return [int(value) for value in text.split(",") if value.strip()]


def report_coverage(
    panel: Annotated[Path, typer.Option(help="Coverage panel directory.")] = Path(
        "data/research/coverage"
    ),
    articles: Annotated[Path, typer.Option(help="Prepared article table.")] = Path(
        "data/processed/articles"
    ),
    links: Annotated[Path, typer.Option(help="Linker output.")] = Path(
        "data/processed/company-links"
    ),
    source: Annotated[Path, typer.Option(help="Raw Fine News shards.")] = Path(
        "data/raw/fine-news"
    ),
    link_metrics: Annotated[Path, typer.Option(help="Company-links metrics.")] = Path(
        "data/research/experiments/company-links/metrics.json"
    ),
    focus: Annotated[Path, typer.Option(help="Company-focus report.")] = Path(
        "data/research/experiments/company-focus"
    ),
    threshold: Annotated[float, typer.Option(help="Operating link score.")] = 0.5,
    min_relevance: Annotated[float, typer.Option(help="Focus rule.")] = 0.0,
    max_offset: Annotated[float, typer.Option(help="Focus rule.")] = 1.0,
    min_mentions: Annotated[int, typer.Option(help="Focus rule.")] = 3,
    complete_from: Annotated[int, typer.Option(help="First full year.")] = 2017,
    complete_through: Annotated[int, typer.Option(help="Last full year.")] = 2025,
    thresholds: Annotated[str, typer.Option(help="Comma-separated counts.")] = (
        "1,12,47,100,250"
    ),
    spans: Annotated[str, typer.Option(help="Comma-separated year spans.")] = "1,3,5,9",
    seed: Annotated[int, typer.Option(help="Near-duplicate sample seed.")] = 43,
    months: Annotated[int, typer.Option(help="Capture months sampled.")] = 6,
    sample_size: Annotated[int, typer.Option(help="Articles sampled.")] = 1000,
    window_days: Annotated[int, typer.Option(help="Publication window.")] = 1,
    max_candidates: Annotated[int, typer.Option(help="Comparisons each.")] = 100,
    jaccard: Annotated[float, typer.Option(help="Near-duplicate similarity.")] = 0.8,
    output: Annotated[Path, typer.Option(help="Report directory.")] = Path(
        "data/research/experiments/coverage"
    ),
) -> None:
    """Write coverage tables, figure data, headline metrics and report.tex."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "tables").mkdir(exist_ok=True)
    complete = range(complete_from, complete_through + 1)
    with duckdb.connect() as con:
        con.execute("SET TimeZone = 'UTC'")
        con.read_parquet(str(articles / "articles.parquet")).create_view("articles")
        con.read_parquet(str(panel / "panel.parquet")).create("panel")
        con.read_parquet(str(panel / "pp_roster.parquet")).create("roster")
        con.execute(
            """CREATE TABLE links AS
            SELECT id, cik, self_publisher,
                   relevance_substantive >= $relevance AND first_offset_share <= $offset
                   AND n_mentions >= $mentions AS focus
            FROM read_parquet($links) WHERE link_score >= $threshold""",
            {
                "links": str(links / "articles" / "*.parquet"),
                "threshold": threshold,
                "relevance": min_relevance,
                "offset": max_offset,
                "mentions": min_mentions,
            },
        )
        panel_rows = _rows(con, "SELECT * FROM panel")
        status = con.sql(
            "SELECT count(*), avg((date_status = 'archival')::INT), "
            "avg((date_status = 'future')::INT) FROM articles"
        ).fetchall()[0]
        settings = {"seed": seed, "months": months, "articles": sample_size}
        settings |= {"window_days": window_days, "max_candidates": max_candidates}
        settings["jaccard"] = jaccard
        data: Row = {
            "funnel": funnel(con),
            "dates": dates(con),
            "screen": screen(con),
            "consecutive": consecutive(
                panel_rows, _integers(thresholds), _integers(spans), complete
            ),
            "breakdowns": breakdowns(con, complete),
            "publishers": publishers(con),
            "near_duplicates": near_duplicates(con, source, settings),
            "ccdf": _ccdf(panel_rows, complete),
            "status_shares": {
                "articles": status[0],
                "archival": status[1],
                "future": status[2],
            },
        }
    quality = {
        "links": json.loads(link_metrics.read_text()),
        "focus": json.loads((focus / "metrics.json").read_text()),
    }
    for name, body in tables(data, quality).items():
        (output / "tables" / f"{name}.tex").write_text(body)
    for name, body in figures(output, data, focus / "curve.csv").items():
        (output / "figures" / f"{name}.tex").write_text(body)
    comparison = data["screen"]["comparison"]
    headline = (
        rf"Of {_number(comparison['roster_raw']['firms'])} Pricing Perspective roster "
        rf"issuers, {_number(comparison['roster_raw']['passing'])} have at least "
        rf"{PP_SCREEN} raw linked articles in every year 2018--2022, "
        rf"{_number(comparison['roster_usable']['passing'])} on usable articles and "
        rf"{_number(comparison['roster_focused']['passing'])} on focused articles. "
        rf"Across all listed issuers, {_number(comparison['all_raw']['passing'])}, "
        rf"{_number(comparison['all_usable']['passing'])} and "
        rf"{_number(comparison['all_focused']['passing'])} issuers pass."
        " Match Group shares its historical CIK with IAC, so 2018--2019 counts "
        "may include coverage of IAC before the separation."
    )
    (output / "report.tex").write_text(report_tex(headline))
    metrics = {
        "funnel": {
            key: sum(row[key] for row in data["funnel"])
            for key in ("articles", "dated", "usable", "linked", "focused")
        },
        "status_shares": data["status_shares"],
        "lag_quantiles": data["dates"]["lag_quantiles"],
        "pp_screen": comparison,
        "roster": data["screen"]["roster"],
        "near_duplicates": data["near_duplicates"],
        "publishers": {
            key: value
            for key, value in data["publishers"].items()
            if key not in ("top", "lorenz")
        },
        "universe_issuer_years": sum(
            row["in_universe"] and row["year"] in complete for row in panel_rows
        ),
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str) + "\n"
    )
    typer.echo(f"Wrote: {output}")
