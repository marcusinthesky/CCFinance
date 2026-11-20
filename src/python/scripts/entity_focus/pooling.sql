CREATE TEMP VIEW scores AS SELECT * FROM read_csv('data/research/experiments/entity-pooling/*.csv', filename=true) WHERE regexp_matches(filename,'/(gemma|open|qwen).csv$');
COPY (
WITH per_story AS (
SELECT model, arm, judge, id, reverse_order, shared_sentence, min(correct) AS ok, avg(margin) AS margin, avg(seconds) AS seconds, avg(passes) AS passes
FROM scores GROUP BY ALL
)
SELECT a.model,a.arm,a.judge,a.reverse_order,a.shared_sentence, count(*) AS n,sum(a.ok) AS successes,
count(*) FILTER(WHERE a.ok>b.ok) AS wins,count(*) FILTER(WHERE a.ok<b.ok) AS losses,avg(a.margin) AS mean_margin,avg(a.seconds) AS seconds,avg(a.passes) AS passes
FROM per_story a JOIN per_story b USING(model,judge,id) WHERE b.arm='sentences'
GROUP BY ALL ORDER BY ALL
) TO 'data/research/experiments/entity-pooling/report.parquet';

CREATE TEMP VIEW totals AS
SELECT model, arm, judge, sum(n) n, sum(successes) successes
FROM 'data/research/experiments/entity-pooling/report.parquet' GROUP BY ALL;

SELECT CASE WHEN count(*) = 4 AND bool_and(n = 25) THEN true
            ELSE error('Unexpected primary denominator') END
FROM totals WHERE judge = 'luna' AND starts_with(arm,'context_');

COPY (
SELECT real.model, real.arm, real.successes AS real_correct, base.successes AS baseline_correct,
       swaps.successes AS swap_pairs_correct,
       real.successes >= base.successes - 1 AND swaps.successes >= 18 AS advance
FROM totals real JOIN totals base ON base.model = real.model AND base.judge = real.judge AND base.arm = 'sentences'
JOIN totals swaps ON swaps.model = real.model AND swaps.arm = real.arm AND swaps.judge = 'fixture'
WHERE real.judge = 'luna' AND starts_with(real.arm, 'context_') AND swaps.n = 24
ORDER BY real.model, real.arm
) TO 'data/research/experiments/entity-pooling/decision.parquet';

SELECT CASE WHEN count(*) = 0 THEN true ELSE error('Incomplete role swap') END
FROM (SELECT model, arm, id FROM scores WHERE judge='fixture' GROUP BY ALL HAVING count(*) <> 2);

SELECT CASE WHEN count(*) = 0 THEN true ELSE error('Invalid pooling score') END
FROM scores WHERE NOT isfinite(margin) OR (arm='context_sentences' AND shared_sentence AND correct=1);
