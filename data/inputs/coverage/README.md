# Coverage audit

The audit measures how much usable, company-focused coverage the staging corpus gives each listed issuer and year. It compares that coverage with the [Pricing Perspective](https://arxiv.org/html/2410.23447v3#Sx1) frame: 100 Nasdaq-100 firms, each with at least 47 raw articles in every year from 2018 to 2022.

## Stages

1. **`prepare_articles`** dates and deduplicates every article (`data/processed/articles/`).
   - **Date status:** a capture within `articles.max_lag_days` (7) of the publication date makes the date `consistent`. A later capture is `archival`: the text was not observably published on its stated date. A publication date more than one day after capture is `future`; one day is allowed for publisher time zones.
   - **Canonical copies:** Fine News already keeps one representative per MinHash cluster (`copies` is the cluster size). Exact text and normalized-URL repeats across monthly captures remain. The earliest capture is canonical.
   - **Usable** articles are canonical and consistently dated.
2. **`snapshot_public_float`** and **`prepare_public_float`** keep SEC `dei:EntityPublicFloat` frames for every quarter. This is the issuer size measure. The snapshot needs network access and `SEC_USER_AGENT`, and is frozen once recorded.
3. **`report_company_focus`** chooses the company-focus rule (`coverage.focus`).
   - **Reference labels:** the model judges' subject role from the seed-43 company-links sample, so no new labels are needed.
   - **Choice:** candidate rules threshold relevance, first-mention position and mention count. The rule with the best development-split F1 is configured.
   - **Evaluation:** test articles score the configured rule end to end, so a focus on a wrong link counts as an error.
4. **`build_coverage_panel`** writes one row per issuer and year (`data/research/coverage/`) with counts at each step of the funnel:
   - raw linked articles;
   - dated;
   - usable;
   - focused.
5. **`report_coverage`** writes tables, figure data, `metrics.json` and `report.tex`. **`render_coverage_report`** builds `report.pdf` with Tectonic from cached resources (run `just latex::setup` once).

## Universe

Most current SEC listings have no start date. An issuer-year is in the universe when either:

- a dated listing covers the year; or
- a current listing of unknown start comes with a public float measured in that year or the year before.

Zero counts are kept for universe members. Linked issuer-years outside the universe, mostly foreign private issuers that report no public float, stay in the panel with `in_universe = false`. Size bands are public-float quintiles within each year.

## Pricing Perspective roster

`pricing-perspective.csv` lists the roster with columns `ticker,name,cik`. `cik` may be blank: tickers map to issuers listed during 2018–2022, preferring Nasdaq listings. An authored CIK overrides the match. `pp_roster.parquet` records each mapping as `matched`, `ambiguous`, `override` or `unmatched`.

## Limits

- **Model labels.** Link and focus accuracy comes from model-adjudicated labels, not human ones.
- **Focus rule.** The rule is moderate: on test articles it finds about 57% of company-focused issuers, and about two thirds of its predictions are correct.
- **Near-duplicates.** The rate is measured within seeded capture months, so pairs that straddle months are missed. The rate is therefore a lower bound.
- **Undated listings.** Firms that listed and delisted within the window without a dated listing or a float are absent from the universe.
