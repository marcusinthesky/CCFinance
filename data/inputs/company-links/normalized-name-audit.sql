-- Run from the repository root in DuckDB. Set baseline_dir to the historical linker output and candidate_dir to the
-- linker output before sourcing this file. The selection is local and read only.
CREATE OR REPLACE TEMP VIEW recovered_pairs AS
WITH recovered AS (
    SELECT id, start, stop, text, cik
    FROM read_parquet(getvariable('candidate_dir') || '/mentions/*.parquet')
    WHERE method = 'normalized_name'
)
SELECT r.*, a.day
FROM recovered r
JOIN read_parquet(getvariable('candidate_dir') || '/articles/*.parquet') a USING (id, cik)
ANTI JOIN (
    SELECT id, cik FROM read_parquet(getvariable('baseline_dir') || '/articles/*.parquet')
    WHERE link_score >= 0.5
) b USING (id, cik)
QUALIFY row_number() OVER (
    PARTITION BY r.id, r.cik ORDER BY sha256('47:' || r.start::VARCHAR)
) = 1;

-- Hold out prior adjudications and the five 2018 issuer groups inspected in
-- development. Exclude at pair level for those five groups, as in the pilot.
CREATE OR REPLACE TEMP VIEW confirmation AS
SELECT * FROM recovered_pairs
WHERE id NOT IN (
    SELECT id FROM 'data/processed/experiments/company-links/sample/mentions.parquet'
    UNION SELECT id FROM 'data/processed/experiments/company-links/sample/articles.parquet'
    UNION SELECT id FROM read_csv_auto(
        '.context/plan/dataset-research/tasks/dataset-requirements/ticker-agreement-seed44.csv'
    )
)
AND NOT (year(day) = 2018 AND cik IN (
    SELECT cik FROM 'data/research/coverage/pp_roster.parquet'
    WHERE ticker IN ('CDNS', 'ENPH', 'IDXX', 'HOLX', 'ORLY')
))
ORDER BY sha256('47:' || id || ':' || cik::VARCHAR)
LIMIT 300;

SELECT count(*) AS eligible_new_pairs FROM recovered_pairs;
SELECT count(*) AS sampled_pairs FROM confirmation;
