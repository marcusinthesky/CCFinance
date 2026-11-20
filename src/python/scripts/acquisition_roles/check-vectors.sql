CREATE TEMP TABLE embeddings AS
SELECT * FROM read_parquet([
  'data/processed/experiments/entity-embeddings/open.parquet',
  'data/processed/experiments/entity-embeddings/qwen.parquet',
  'data/processed/experiments/entity-embeddings/gemma.parquet'
]);
SELECT CASE WHEN count(*) = count(DISTINCT (id,cik,model,arm))
    AND count_if((text IS NULL) != (vector IS NULL)) = 0
    AND count_if(vector IS NOT NULL AND (
        len(vector) != CASE model WHEN 'gemma' THEN 768 WHEN 'qwen' THEN 1024 ELSE 2048 END
        OR NOT isfinite(list_inner_product(vector,vector))
        OR abs(list_inner_product(vector,vector)-1) > 0.0001)) = 0
    THEN true ELSE error('Invalid embedding key or vector') END FROM embeddings;
SELECT CASE WHEN count_if(
  replace(a.text,'title: none | text: ','title: '||s.title||' | text: ')
  IS DISTINCT FROM b.text) = 0 THEN true ELSE error('Gemma title ablation mismatch') END
FROM embeddings a JOIN embeddings b ON (a.id,a.cik,a.model)=(b.id,b.cik,b.model)
  AND b.arm=a.arm||'-title'
JOIN 'data/processed/experiments/entity-embeddings/acquisition-screen.parquet' s ON s.id=a.id
WHERE a.model='gemma';
SELECT CASE WHEN count_if(a.text IS DISTINCT FROM b.text) = 0
  THEN true ELSE error('Content-matched baseline mismatch') END
FROM embeddings a JOIN embeddings b USING (id,cik,arm)
WHERE a.model='open' AND b.model='qwen' AND arm IN ('mentions','fact');
