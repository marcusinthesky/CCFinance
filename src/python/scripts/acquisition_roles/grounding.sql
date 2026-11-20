COPY (
    SELECT f.id, f.ciks[1] AS cik,
           list_filter(s.firms, lambda item: item.cik = f.ciks[1])[1].name AS issuer,
           f.statement, f.quote
    FROM read_json_auto('data/processed/experiments/entity-embeddings/facts.json') f
    JOIN 'data/processed/experiments/entity-embeddings/acquisition-screen.parquet' s USING (id)
    WHERE f.statement IS NOT NULL
    ORDER BY sha256(f.id || '/' || f.ciks[1]), f.id, cik
    LIMIT 20
) TO 'data/processed/experiments/entity-embeddings/grounding-review.parquet';
