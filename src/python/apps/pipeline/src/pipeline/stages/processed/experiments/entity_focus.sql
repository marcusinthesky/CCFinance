-- Freeze the two-issuer evaluation frame, split manifest and article inputs.
SET threads=2;
CREATE TEMP TABLE roster AS
SELECT DISTINCT cik FROM 'data/research/coverage/pp_roster.parquet' WHERE cik IS NOT NULL;

CREATE TEMP TABLE frame AS
SELECT a.id, year(a.published) AS yr, count(*) AS n_issuers, count(r.cik) AS n_roster
FROM read_parquet('data/processed/articles/articles.parquet') a
JOIN read_parquet('data/processed/company-links/articles/*.parquet') l USING (id)
LEFT JOIN roster r USING (cik)
WHERE a.usable AND year(a.published) BETWEEN 2018 AND 2022
  AND l.link_score >= 0.5 AND NOT l.self_publisher
GROUP BY a.id, yr;

COPY (
    SELECT yr, count(*) AS linked, count_if(n_issuers >= 2) AS multi_issuer,
           count_if(n_issuers >= 2 AND n_roster >= 1) AS multi_including_roster,
           count_if(n_roster >= 2) AS multi_roster
    FROM frame GROUP BY yr ORDER BY yr
) TO 'data/processed/experiments/entity-focus/frame.csv' (HEADER);

CREATE TEMP TABLE sample AS
WITH prior AS (
    SELECT id FROM 'data/processed/experiments/company-links/sample/articles.parquet'
    UNION SELECT id FROM 'data/processed/experiments/company-links/sample/mentions.parquet'
), candidates AS (
    SELECT f.*, CASE WHEN n_roster = 1 THEN 'one roster' ELSE 'multiple roster' END AS stratum
    FROM frame f ANTI JOIN prior USING (id)
    WHERE n_issuers >= 2 AND n_roster >= 1
)
SELECT *, count(*) OVER (PARTITION BY yr, stratum) AS stratum_total
FROM candidates
QUALIFY row_number() OVER (
    PARTITION BY yr, stratum ORDER BY sha256('ccf-entity-test-v1/' || id), id
) <= 25;

COPY (
    WITH pairs AS (
        SELECT s.id,
               list(l.cik ORDER BY sha256('ccf-issuer-v1/' || s.id || '/' || l.cik), l.cik)
                   FILTER (WHERE r.cik IS NOT NULL) AS in_roster,
               list(l.cik ORDER BY sha256('ccf-issuer-v1/' || s.id || '/' || l.cik), l.cik)
                   FILTER (WHERE r.cik IS NULL) AS outside_roster
        FROM sample s JOIN read_parquet('data/processed/company-links/articles/*.parquet') l USING (id)
        LEFT JOIN roster r USING (cik)
        WHERE l.link_score >= 0.5 AND NOT l.self_publisher
        GROUP BY s.id
    )
    SELECT s.id, a.published, a.host, s.yr, s.stratum, s.stratum_total, s.n_issuers, s.n_roster,
           p.in_roster[1] AS cik_a,
           CASE WHEN s.n_roster >= 2 THEN p.in_roster[2] ELSE p.outside_roster[1] END AS cik_b
    FROM sample s JOIN pairs p USING (id)
    JOIN read_parquet('data/processed/articles/articles.parquet') a USING (id)
    ORDER BY s.yr, s.stratum, s.id
) TO 'data/processed/experiments/entity-focus/manifest.csv' (HEADER);
COPY (
WITH ranked AS (
SELECT *, row_number() OVER(PARTITION BY yr,stratum ORDER BY sha256('entity-focus-v1/'||id),id) AS pos
FROM 'data/processed/experiments/entity-focus/manifest.csv'
), pairs AS (
SELECT s.id, list(struct_pack(cik:=l.cik,name:=i.name,ticker:=l.ticker,
    spans:=list_transform(list_filter(l.evidence,lambda e:e.score>=0.5),lambda e:struct_pack(start:=e.start,stop:=e.stop)))
    ORDER BY sha256('ordered/'||s.id||l.cik)) AS firms
FROM ranked s JOIN read_parquet('data/processed/company-links/articles/*.parquet') l USING(id)
JOIN 'data/processed/issuers/issuers.parquet' i USING(cik) WHERE l.cik IN (s.cik_a,s.cik_b) GROUP BY s.id
)
SELECT s.id,s.yr,s.stratum,s.stratum_total,s.pos<=10 AS dev,s.pos BETWEEN 11 AND 15 AS audit,
n.metadata.duplicate_group_id AS story,n.metadata.title AS title,n.text AS body,p.firms
FROM ranked s JOIN pairs p USING(id) JOIN read_parquet('data/raw/fine-news/*/*/*.parquet') n USING(id)
ORDER BY s.id
) TO 'data/processed/experiments/entity-focus/sample.parquet';
