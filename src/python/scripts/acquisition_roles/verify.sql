SELECT CASE WHEN count(*) = 80 AND count_if(audit) = 20 AND
sha256(string_agg(id || '/' || firms[1].cik || '/' || firms[2].cik || '/' || audit::INT,'|' ORDER BY id))
= 'c2a2b437175f0379e72c7c1bcd9688b806c145170d0d615e0503541b58216203'
THEN true ELSE error('Frozen manifest mismatch') END
FROM 'data/processed/experiments/entity-embeddings/acquisition-screen.parquet';
