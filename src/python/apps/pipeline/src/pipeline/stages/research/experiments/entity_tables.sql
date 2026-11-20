-- Each table retains its own unit of analysis and denominator.
COPY (
 SELECT c.model,c.reference,c.n,c.arm,c.correct FROM 'data/research/experiments/entity-focus/comparison.csv' c,
 read_json_auto('data/research/experiments/entity-focus/decision.json') d
 WHERE c.cohort='full' AND c.reference IN ('luna_masked','terra_masked')
 AND (c.arm IN ('header','sentences') OR c.arm=json_extract_string(to_json(d.selection),'$.'||c.model))
 ORDER BY ALL
) TO 'data/research/experiments/entity-paper/entity-focus.csv' (HEADER);

COPY (
 SELECT model,arm,count(DISTINCT block) AS independent_deal_pairs,count(*) AS comparisons,avg(score) AS accuracy
 FROM 'data/research/experiments/acquisition-roles/comparisons.parquet'
 GROUP BY ALL ORDER BY ALL
) TO 'data/research/experiments/entity-paper/acquisitions.csv' (HEADER);

COPY (
 SELECT model,arm,judge,sum(n)::INTEGER AS stories_or_swap_pairs,sum(successes)::INTEGER AS correct
 FROM 'data/research/experiments/entity-pooling/report.parquet'
 GROUP BY ALL ORDER BY ALL
) TO 'data/research/experiments/entity-paper/pooling.csv' (HEADER);
