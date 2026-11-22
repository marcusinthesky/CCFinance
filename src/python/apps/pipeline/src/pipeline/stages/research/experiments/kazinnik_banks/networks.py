"""Build Kazinnik bank networks from unique article and bank memberships."""

import csv
from html import escape
from pathlib import Path
from typing import Annotated

import duckdb
import numpy as np
import typer


def build_networks(
    con: duckdb.DuckDBPyConnection,
    bridge: Path,
    inputs: Path,
) -> None:
    """Create study memberships, undirected edges and group-pair statistics."""
    con.execute(
        """CREATE TABLE windows AS
        SELECT * FROM read_csv($windows, types={
            'starts_on': 'DATE', 'ends_on': 'DATE'
        });
        """,
        {"windows": str(inputs / "windows.csv")},
    )
    con.execute(
        """CREATE TABLE roster AS
        SELECT r.*, EXISTS (SELECT 1 FROM read_csv($crosswalk) x
            WHERE r.bank = x.bank) AS mapped,
            EXISTS (SELECT 1 FROM read_csv($crosswalk) x
            WHERE r.bank = x.bank AND x.scope <> 'foreign_parent') AS direct_mapping
        FROM read_csv($roster) r""",
        {
            "roster": str(inputs / "roster.csv"),
            "crosswalk": str(inputs / "crosswalk.csv"),
        },
    )
    con.execute(
        """CREATE TABLE article_banks AS
        SELECT DISTINCT id, bank, published, directly_mapped, publisher, capture_month,
               article_form, headline, normalized_headline, author, url,
               minhash_cluster_id, text_hash
        FROM read_parquet($bridge)""",
        {"bridge": str(bridge)},
    )
    con.execute(
        """CREATE TABLE window_articles AS
        WITH counts AS (
            SELECT w.study_window, w.period, a.* EXCLUDE (directly_mapped, bank),
                   count(*) AS bank_count
            FROM article_banks a
            JOIN windows w ON a.published BETWEEN w.starts_on AND w.ends_on
            GROUP BY ALL
        )
        SELECT *,
            row_number() OVER (
                PARTITION BY study_window, normalized_headline
                ORDER BY bank_count DESC, published, id
            ) AS headline_rank,
            count(DISTINCT publisher) OVER (
                PARTITION BY study_window, normalized_headline
            ) AS headline_publishers
        FROM counts;
        CREATE TABLE variants (variant VARCHAR);
        INSERT INTO variants VALUES ('baseline'), ('unique_headline'),
            ('under_six_banks'), ('exclude_roundups'), ('reporting'),
            ('reuters_host'), ('exclude_nasdaq'), ('direct_only');
        CREATE TABLE memberships AS
        SELECT v.variant, a.study_window, a.id, b.bank, r.bank_order
        FROM window_articles a JOIN article_banks b USING (id)
        JOIN roster r USING (bank)
        CROSS JOIN variants v
        WHERE CASE v.variant
            WHEN 'baseline' THEN true
            WHEN 'unique_headline'
                THEN a.normalized_headline IS NULL OR a.headline_rank = 1
            WHEN 'under_six_banks' THEN a.bank_count < 6
            WHEN 'exclude_roundups' THEN a.article_form IS DISTINCT FROM 'roundup'
            WHEN 'reporting' THEN a.article_form = 'reporting'
            WHEN 'reuters_host'
                THEN regexp_matches(a.publisher, '(^|[.])reuters[.]com$')
            WHEN 'exclude_nasdaq'
                THEN NOT regexp_matches(a.publisher, '(^|[.])nasdaq[.]com$')
            WHEN 'direct_only' THEN b.directly_mapped
        END;
        CREATE TABLE article_pairs AS
        SELECT m.variant, m.study_window, m.id, m.bank AS bank_a, n.bank AS bank_b
        FROM memberships m JOIN memberships n ON (
            m.variant = n.variant AND m.study_window = n.study_window
            AND m.id = n.id AND m.bank_order < n.bank_order
        );
        CREATE TABLE edges AS
        SELECT study_window, variant, bank_a, bank_b, count(*) AS weight
        FROM article_pairs GROUP BY ALL;
        """,
    )
    _summarize_pairs(con)


def _summarize_pairs(con: duckdb.DuckDBPyConnection) -> None:
    """Tabulate edge density against published and observable pair universes."""
    con.execute(
        """CREATE TABLE pair_universe AS
        SELECT DISTINCT category, a.bank AS bank_a, b.bank AS bank_b,
               a.mapped AND b.mapped AS mapped,
               a.direct_mapping AND b.direct_mapping AS direct_mapping
        FROM roster a JOIN roster b ON a.bank_order < b.bank_order
        CROSS JOIN LATERAL (
            SELECT CASE WHEN a.bank_group = b.bank_group THEN 'Within ' || a.bank_group
                        ELSE least(a.bank_group, b.bank_group) || ' / ' ||
                             greatest(a.bank_group, b.bank_group) END AS category
            UNION ALL SELECT 'Between ' || a.bank_group
            WHERE a.bank_group <> b.bank_group
            UNION ALL SELECT 'Between ' || b.bank_group
            WHERE a.bank_group <> b.bank_group
            UNION ALL SELECT 'Within Non-Big 6'
            WHERE a.bank_group <> 'Big 6' AND b.bank_group <> 'Big 6'
            UNION ALL SELECT 'Total'
        ) u;
        CREATE TABLE group_pairs AS
        SELECT w.study_window, w.period, v.variant, p.category,
               count(*) AS reference_possible_pairs,
               count(*) FILTER (
                   WHERE CASE WHEN v.variant = 'direct_only' THEN p.direct_mapping
                              ELSE p.mapped END
               ) AS mapped_possible_pairs,
               count(e.weight) AS connected_pairs,
               coalesce(sum(e.weight), 0)::BIGINT AS pair_weight,
               round(count(e.weight) / nullif(count(*) FILTER (
                   WHERE CASE WHEN v.variant = 'direct_only' THEN p.direct_mapping
                              ELSE p.mapped END
               ), 0), 6) AS mapped_density
        FROM windows w CROSS JOIN variants v CROSS JOIN pair_universe p
        LEFT JOIN edges e USING (study_window, variant, bank_a, bank_b)
        GROUP BY ALL;
        CREATE TABLE bank_activity AS
        WITH bank_counts AS (
            SELECT study_window, variant, bank, count(*) AS article_count
            FROM memberships GROUP BY ALL
        ), neighbors AS (
            SELECT study_window, variant, bank, count(*) AS degree,
                   sum(weight)::BIGINT AS strength
            FROM (
                SELECT study_window, variant, bank_a AS bank, weight FROM edges
                UNION ALL
                SELECT study_window, variant, bank_b AS bank, weight FROM edges
            ) GROUP BY ALL
        ), counts AS (
            SELECT w.study_window, v.variant, r.* EXCLUDE (mapped, direct_mapping),
                   CASE WHEN v.variant = 'direct_only' THEN r.direct_mapping
                        ELSE r.mapped END AS mapped,
                   coalesce(c.article_count, 0) AS article_count,
                   coalesce(n.degree, 0) AS degree, coalesce(n.strength, 0) AS strength
            FROM windows w CROSS JOIN variants v CROSS JOIN roster r
            LEFT JOIN bank_counts c USING (study_window, variant, bank)
            LEFT JOIN neighbors n USING (study_window, variant, bank)
        )
        SELECT * EXCLUDE (article_count, degree, strength),
               CASE WHEN NOT mapped THEN 'unresolved'
                    WHEN article_count = 0 THEN 'mapped_no_articles'
                    ELSE 'mapped_active' END AS activity,
               CASE WHEN mapped THEN article_count END AS article_count,
               CASE WHEN mapped THEN degree END AS degree,
               CASE WHEN mapped THEN strength END AS strength
        FROM counts;
        """,
    )


def _write_tables(con: duckdb.DuckDBPyConnection, output: Path) -> None:
    """Export group comparisons and publication and article-size diagnostics."""
    queries = {
        "edges": """SELECT * FROM edges
            ORDER BY study_window, variant, weight DESC, bank_a, bank_b""",
        "bank-activity": """SELECT * FROM bank_activity
            ORDER BY study_window, variant, bank_order""",
        "group-pairs": "SELECT * FROM group_pairs ORDER BY ALL",
        "comparisons": """SELECT j.period, j.variant, j.category,
            j.reference_possible_pairs,
            j.mapped_possible_pairs, j.connected_pairs AS january_connected,
            a.connected_pairs AS april_connected,
            a.connected_pairs - j.connected_pairs AS connected_change,
            j.pair_weight AS january_weight, a.pair_weight AS april_weight,
            a.pair_weight - j.pair_weight AS pair_weight_change
            FROM group_pairs j JOIN group_pairs a USING (period, variant, category)
            WHERE starts_with(j.study_window, 'jan_')
              AND starts_with(a.study_window, 'apr_')
            ORDER BY ALL""",
        "group-coverage": """SELECT study_window, variant, bank_group,
            count(*) AS reference_banks, count(*) FILTER (WHERE mapped) AS mapped_banks,
            count(*) FILTER (WHERE activity = 'mapped_active') AS active_banks,
            count(*) FILTER (WHERE activity = 'mapped_no_articles')
                AS mapped_no_articles,
            count(*) FILTER (WHERE activity = 'unresolved') AS unresolved_banks
            FROM bank_activity GROUP BY ALL ORDER BY ALL""",
        "publisher-concentration": """SELECT study_window, publisher,
            count(*) AS articles,
            count(*) FILTER (WHERE bank_count > 1) AS multi_bank_articles,
            sum(bank_count * (bank_count - 1) // 2)::BIGINT AS pair_weight,
            round(sum(bank_count * (bank_count - 1) // 2) / nullif(
                sum(sum(bank_count * (bank_count - 1) // 2))
                    OVER (PARTITION BY study_window), 0), 6) AS share_of_pair_weight
            FROM window_articles GROUP BY study_window, publisher
            ORDER BY study_window, pair_weight DESC, publisher""",
        "article-size": """SELECT study_window, bank_count, count(*) AS articles,
            sum(bank_count * (bank_count - 1) // 2)::BIGINT AS pair_weight,
            round(sum(bank_count * (bank_count - 1) // 2) / nullif(
                sum(sum(bank_count * (bank_count - 1) // 2))
                    OVER (PARTITION BY study_window), 0), 6) AS share_of_pair_weight
            FROM window_articles GROUP BY study_window, bank_count
            ORDER BY study_window, bank_count""",
        "article-form": """SELECT study_window, article_form, count(*) AS articles,
            sum(bank_count * (bank_count - 1) // 2)::BIGINT AS pair_weight
            FROM window_articles GROUP BY ALL ORDER BY ALL""",
        "article-pairs": """SELECT p.study_window, p.bank_a, p.bank_b, p.id,
            a.published, a.publisher, a.bank_count, a.article_form,
            a.capture_month, a.url, a.headline
            FROM article_pairs p JOIN window_articles a USING (study_window, id)
            WHERE p.variant = 'baseline' ORDER BY ALL""",
        "large-edge-articles": """WITH largest AS (
            SELECT * FROM edges WHERE variant = 'baseline'
            QUALIFY row_number() OVER (
                PARTITION BY study_window ORDER BY weight DESC, bank_a, bank_b
            ) <= 5
            )
            SELECT l.study_window, l.bank_a, l.bank_b, l.weight, a.id,
                   a.published, a.publisher, a.author, a.headline, a.url, a.bank_count
            FROM largest l JOIN article_pairs p
                USING (study_window, variant, bank_a, bank_b)
            JOIN window_articles a USING (study_window, id)
            ORDER BY l.study_window, l.weight DESC, l.bank_a, l.bank_b,
                     a.published, a.id""",
        "headline-groups": """SELECT study_window, normalized_headline, headline_rank,
            headline_publishers, id, published, publisher, author, bank_count,
            headline, url, minhash_cluster_id, text_hash
            FROM window_articles
            WHERE normalized_headline IS NOT NULL AND headline_publishers > 1
            ORDER BY study_window, normalized_headline, headline_rank""",
    }
    for name, query in queries.items():
        con.execute(
            f"COPY ({query}) TO $path (FORMAT CSV, HEADER TRUE)",
            {"path": str(output / f"{name}.csv")},
        )


def _paired_heatmap(
    output: Path,
    period: str,
    banks: list[str],
    arrays: list[np.ndarray[tuple[int, int], np.dtype[np.float64]]],
    mapped: frozenset[str],
) -> None:
    """Draw two labeled baseline matrices with one linear color scale."""
    cell, origin_y, graph_gap = 12, 94, 76
    graph = cell * len(banks)
    lefts = (62, 62 + graph + graph_gap)
    width = lefts[1] + graph + 18
    height = origin_y + graph + 66
    max_weight = max(int(array.max()) for array in arrays)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">Kazinnik bank networks, January and April '
        f"{period}s</title>",
        '<desc id="desc">Bank-pair article counts with a common linear scale. '
        "Hatching denotes unresolved banks and gray denotes the diagonal.</desc>",
        '<defs><pattern id="unresolved" width="4" height="4" '
        'patternUnits="userSpaceOnUse">'
        '<rect width="4" height="4" fill="#f2f4f7"/>'
        '<path d="M0 4L4 0" stroke="#929aaa"/>'
        "</pattern></defs>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<g font-family="sans-serif" fill="#172933">',
    ]
    for month, left, array in zip(("January", "April"), lefts, arrays, strict=True):
        svg.append(
            f'<text x="{left}" y="22" font-size="15">{month} 2020 · {period}</text>'
        )
        for i, bank in enumerate(banks):
            x, y = left + i * cell + 8, origin_y + i * cell + 9
            label = escape(bank)
            svg.extend(
                (
                    f'<text x="{left - 4}" y="{y}" font-size="8" '
                    f'text-anchor="end">{label}</text>',
                    f'<text font-size="8" '
                    f'transform="translate({x},{origin_y - 4}) rotate(-60)">'
                    f"{label}</text>",
                )
            )
            for j, other in enumerate(banks):
                value = int(array[i, j])
                fill = _weight_color(value, max_weight)
                description = str(value)
                if bank not in mapped or other not in mapped:
                    fill = "url(#unresolved)"
                    description = "unresolved"
                elif i == j:
                    fill = "#d7dce0"
                    description = "diagonal"
                svg.append(
                    f'<rect x="{left + j * cell}" y="{origin_y + i * cell}" '
                    f'width="{cell}" height="{cell}" fill="{fill}" '
                    f'stroke="#e1e6eb" stroke-width=".35">'
                    f"<title>{label} and {escape(other)}: {description}</title>"
                    "</rect>",
                )
    y = height - 38
    for tick in range(7):
        value = round(max_weight * tick / 6)
        x = 62 + 33 * tick
        fill = _weight_color(value, max_weight)
        svg.append(
            f'<rect x="{x}" y="{y}" width="33" height="11" fill="{fill}"/>'
            f'<text x="{x + 16}" y="{y + 25}" font-size="9" '
            f'text-anchor="middle">{value}</text>',
        )
    svg.append(
        f'<text x="315" y="{y + 10}" font-size="11">Articles per pair</text>'
        f'<rect x="450" y="{y}" width="11" height="11" fill="url(#unresolved)" />'
        f'<text x="466" y="{y + 10}" font-size="11">Unresolved</text>'
        f'<rect x="568" y="{y}" width="11" height="11" fill="#d7dce0" />'
        f'<text x="584" y="{y + 10}" font-size="11">Diagonal</text></g></svg>',
    )
    output.write_text("\n".join(svg) + "\n", encoding="utf-8")


def _weight_color(value: int, maximum: int) -> str:
    """Interpolate between white and dark blue on a common linear scale."""
    scale = value / maximum if maximum else 0.0
    return "#" + "".join(
        f"{round(255 - (255 - channel) * scale):02x}" for channel in (16, 72, 121)
    )


def _write_matrices(con: duckdb.DuckDBPyConnection, output: Path) -> None:
    """Write baseline matrices and heatmaps, plus centrality for every variant."""
    ordered = con.execute(
        "SELECT bank, mapped FROM roster ORDER BY bank_order"
    ).fetchall()
    banks: list[str] = [bank for bank, _ in ordered]
    mapped: frozenset[str] = frozenset(bank for bank, observed in ordered if observed)
    order = {bank: index for index, bank in enumerate(banks)}
    centrality = []
    results = con.execute(
        "SELECT study_window, variant FROM group_pairs GROUP BY ALL ORDER BY ALL",
    ).fetchall()
    matrices = {}
    for window, variant in results:
        array = np.zeros((len(banks), len(banks)))
        for bank_a, bank_b, weight in con.execute(
            """SELECT bank_a, bank_b, weight FROM edges
            WHERE study_window = $window AND variant = $variant""",
            {"window": window, "variant": variant},
        ).fetchall():
            i, j = order[bank_a], order[bank_b]
            array[i, j] = array[j, i] = weight
        if variant == "baseline":
            matrices[window] = array

        values, vectors = np.linalg.eigh(array)
        identified = values[-1] > 0 and not np.isclose(values[-1], values[-2])
        scores = np.abs(vectors[:, -1])
        observed_banks = con.execute(
            """SELECT bank, mapped FROM bank_activity
            WHERE study_window = $window AND variant = $variant ORDER BY bank_order""",
            {"window": window, "variant": variant},
        ).fetchall()
        centrality.extend(
            (
                window,
                variant,
                bank,
                round(float(score), 8) if identified and observed else None,
            )
            for (bank, observed), score in zip(observed_banks, scores, strict=True)
        )
    with (output / "eigenvector-centrality.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("study_window", "variant", "bank", "eigenvector_centrality"))
        writer.writerows(centrality)

    for period in ("week", "month"):
        arrays: list[np.ndarray[tuple[int, int], np.dtype[np.float64]]] = []
        for month in ("jan", "apr"):
            window = f"{month}_{period}"
            array = matrices[window]
            records = ["," + ",".join(banks)]
            for bank, row in zip(banks, array, strict=True):
                counts = [
                    str(int(weight)) if bank in mapped and other in mapped else ""
                    for other, weight in zip(banks, row, strict=True)
                ]
                records.append(bank + "," + ",".join(counts))
            (output / f"{window}-matrix.csv").write_text(
                "\n".join(records) + "\n",
                encoding="utf-8",
            )
            arrays.append(array)
        _paired_heatmap(
            output / f"{period}-heatmaps.svg", period, banks, arrays, mapped
        )


def report_kazinnik_banks(
    source: Annotated[
        Path, typer.Option(help="Prepared article and bank membership directory.")
    ],
    inputs: Annotated[Path, typer.Option(help="Roster, crosswalk and study windows.")],
    output: Annotated[Path, typer.Option(help="Report directory.")],
) -> None:
    """Write bank edges, article counts, group comparisons, matrices and heatmaps."""
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": 4}) as con:
        build_networks(con, source / "article_banks.parquet", inputs)
        _write_tables(con, output)
        _write_matrices(con, output)
