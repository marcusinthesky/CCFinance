SET threads=2;
CREATE TEMP TABLE pairs AS
SELECT id,cik FROM 'data/processed/experiments/lopez-lira-tang-sample/sample.parquet';
COPY (
    WITH offsets AS (
        SELECT id, list(struct_pack(cik := cik, third_stop := evidence[3].stop)
                        ORDER BY cik) AS issuers
        FROM 'data/processed/company-links/articles/*.parquet' JOIN pairs USING(id,cik)
        GROUP BY id
    )
    SELECT id,text,issuers FROM 'data/raw/fine-news/*/eng_Latn/*.parquet'
    JOIN offsets USING(id) ORDER BY id
) TO '.runtime/overnight-audit/bodies.jsonl' (FORMAT JSON);
