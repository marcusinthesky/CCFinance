-- Run from the repository root. The result is a local review packet with
-- unordered issuer identities and the accepted spans for local embedding.
SET threads = 3;

COPY (
WITH stories AS MATERIALIZED (
    SELECT n.id, a.published, n.metadata.title AS title, n.text AS body,
           ' ' || trim(regexp_replace(lower(n.metadata.title), '[^a-z0-9]+', ' ', 'g')) || ' ' AS headline
    FROM read_parquet(['data/raw/fine-news/201[89]-*/eng_Latn/*.parquet',
                       'data/raw/fine-news/202[012]-*/eng_Latn/*.parquet']) n
    JOIN 'data/processed/articles/articles.parquet' a USING (id)
    ANTI JOIN 'data/processed/experiments/company-links/sample/articles.parquet' s USING (id)
    WHERE a.usable AND year(a.published) BETWEEN 2018 AND 2022
      AND length(n.text) BETWEEN 300 AND 6000
      AND regexp_matches(lower(n.metadata.title),
              '\b(acquire[sd]?|acquiring|acquisition|buyout|takeover|to buy|buys|to purchase)\b')
), linked AS (
    SELECT s.*, l.cik, i.name, list_filter(l.evidence, lambda e: e.score >= 0.5) AS spans
    FROM stories s
    JOIN read_parquet('data/processed/company-links/articles/*.parquet') l USING (id)
    JOIN 'data/processed/issuers/issuers.parquet' i USING (cik)
    WHERE l.link_score >= 0.5 AND NOT l.self_publisher AND i.name IS NOT NULL
), named AS (
    SELECT l.* FROM linked l
    WHERE EXISTS (
        SELECT 1 FROM unnest(l.spans) t(e),
        LATERAL (SELECT trim(regexp_replace(lower(l.body[e.start+1:e.stop]), '[^a-z0-9]+', ' ', 'g')) AS surface)
        WHERE length(surface) >= 3 AND contains(l.headline, ' ' || surface || ' ')
    )
), pairs AS (
    SELECT id, any_value(published) AS published, any_value(title) AS title,
           any_value(body) AS body, min(cik) AS lo, max(cik) AS hi,
           list(struct_pack(cik:=cik, name:=name,
                            spans:=list_transform(spans,lambda e:struct_pack(start:=e.start,stop:=e.stop)))
                ORDER BY sha256('role-audit-issuer-1/' || id || '/' || cik), cik) AS firms,
           sha256('role-audit-article-1/' || id) AS priority
    FROM named
    GROUP BY id HAVING count(*) = 2
), new_pairs AS (
    SELECT * FROM pairs
    -- All eight buyer/target pairs seen in the June development experiment.
    WHERE (lo, hi) NOT IN ((804328,1413447),(732717,1105705),(1551152,1578845),
                          (1108524,1303652),(36966,933141),(789019,1002517),
                          (82166,1567094),(1158463,1498710))
    QUALIFY row_number() OVER (PARTITION BY lo,hi ORDER BY priority,id) = 1
), first_per_issuer AS (
    SELECT id FROM new_pairs, unnest([lo,hi]) t(cik)
    QUALIFY row_number() OVER (PARTITION BY cik ORDER BY priority,id) = 1
), disjoint AS (
    SELECT n.* FROM new_pairs n
    JOIN (SELECT id FROM first_per_issuer GROUP BY id HAVING count(*) = 2) d USING (id)
), sampled AS (
    SELECT *, year(published) AS yr, count(*) OVER (PARTITION BY year(published)) AS available
    FROM disjoint
    QUALIFY row_number() OVER (PARTITION BY year(published) ORDER BY priority,id) <= 16
)
SELECT id, published, yr, available, title, body, firms,
       row_number() OVER (PARTITION BY yr ORDER BY sha256('role-audit-repeat-1/' || id),id) <= 4 AS audit
FROM sampled ORDER BY yr, priority, id
) TO 'data/processed/experiments/entity-embeddings/acquisition-screen.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
