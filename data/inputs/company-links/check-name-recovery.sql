-- Set baseline_shard and candidate_shard to corresponding mention Parquet files.
-- Each row has one original span; a passing shard returns zero violations.
WITH original AS (FROM read_parquet(getvariable('baseline_shard'))),
     candidate AS (FROM read_parquet(getvariable('candidate_shard'))),
     compared AS (
         SELECT b, a FROM original b FULL JOIN candidate a USING (id, start)
     )
SELECT count(*) FILTER (WHERE
    b.id IS NULL OR a.id IS NULL
    OR row(b.stop, b.text, b.key) IS DISTINCT FROM row(a.stop, a.text, a.key)
    OR CASE WHEN a.method = 'normalized_name' THEN
        b.method IS DISTINCT FROM 'unresolved' OR b.cik IS NOT NULL
        OR a.cik IS NULL OR a.link_score IS DISTINCT FROM 1.0
    ELSE
        row(b.method, b.cik, b.link_score, b.self_publisher)
            IS DISTINCT FROM row(a.method, a.cik, a.link_score, a.self_publisher)
        OR list_transform(b.candidates, x -> x.cik)
            IS DISTINCT FROM list_transform(a.candidates, x -> x.cik)
        OR coalesce(list_max(list_transform(list_zip(b.candidates, a.candidates),
            x -> abs(x[1].score - x[2].score))), 0.0) > 1e-16
    END
) AS violations FROM compared;
