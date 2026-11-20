-- Recreate the eight development inputs under .runtime/role-rehearsal/.
CREATE TEMP TABLE truth(article_key VARCHAR, buyer BIGINT, target BIGINT);
INSERT INTO truth VALUES
('44db69a4',804328,1413447),('6f48578f',732717,1105705),
('0a3801b1',1551152,1578845),('9b4a2a4e',1108524,1303652),
('4cf73b25',36966,933141),('6fcab3b8',789019,1002517),
('95acf8fe',1567094,82166),('83d4d149',1158463,1498710);
CREATE TEMP TABLE sample AS
SELECT n.id,n.metadata.title AS title,n.text AS body,t.buyer,t.target
FROM read_parquet(['data/raw/fine-news/201[89]-06/eng_Latn/*.parquet',
                   'data/raw/fine-news/202[012]-06/eng_Latn/*.parquet']) n
JOIN truth t ON substr(n.id,11,8)=t.article_key;
SELECT CASE WHEN count(*)=8 THEN true ELSE error('Development IDs changed') END FROM sample;
COPY (
  SELECT s.id,any_value(s.title) AS title,any_value(s.body) AS body,
         list(struct_pack(cik:=l.cik,spans:=list_filter(l.evidence,lambda e:e.score>=0.5))
              ORDER BY l.cik) AS firms
  FROM sample s JOIN read_parquet('data/processed/company-links/articles/*-06*.parquet') l USING(id)
  WHERE l.cik IN (s.buyer,s.target) AND l.link_score>=0.5 AND NOT l.self_publisher
  GROUP BY s.id
) TO '.runtime/role-rehearsal/acquisition-screen.parquet';
COPY (SELECT id,'primary' AS role,'A_buys_B' AS direction,[buyer,target] AS ciks FROM sample)
TO '.runtime/role-rehearsal/labels.json' (FORMAT JSON, ARRAY true);
COPY (SELECT id,[cik] AS ciks,NULL::VARCHAR AS statement FROM sample,unnest([buyer,target]) t(cik))
TO '.runtime/role-rehearsal/facts.json' (FORMAT JSON, ARRAY true);
