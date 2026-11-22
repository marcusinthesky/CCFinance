-- One unit of entry notional per active equal-weighted leg. Charge on both trades.
CREATE TEMP TABLE drift AS
WITH pairs AS (
    FROM 'data/research/experiments/lopez-lira-tang-title-probes/paired_days.csv'
    WHERE reference='body' AND target='drift' AND evaluated
)
SELECT 'body' AS sample, session, reference_long_leg+reference_short_leg AS legs,
       reference_return*10000 AS gross_bp FROM pairs WHERE variant='gemma_title'
UNION ALL
SELECT variant, session, variant_long_leg+variant_short_leg, variant_return*10000 FROM pairs;

CREATE TEMP TABLE costs AS
SELECT sample, one_way_bp, count(*) AS evaluated_days, count_if(legs=0) AS zero_leg_days,
    avg(legs) AS mean_active_legs, avg(gross_bp-2*legs*one_way_bp) AS net_mean_bp,
    sum(gross_bp)/(2*sum(legs)) AS break_even_one_way_bp
FROM drift CROSS JOIN (VALUES (0),(1),(5),(10),(25)) t(one_way_bp)
GROUP BY sample,one_way_bp;
SELECT CASE WHEN count(*)=3 AND bool_and(c.evaluated_days=p.evaluated_days
    AND c.zero_leg_days=p.evaluated_zero_leg_days AND abs(net_mean_bp-mean_return*10000)<1e-10)
    THEN true ELSE error('Drift return or support differs from frozen portfolios') END AS reconciled
FROM costs c JOIN 'data/research/experiments/lopez-lira-tang-title-probes/portfolios.csv' p USING(sample)
WHERE p.target='drift' AND c.one_way_bp=0;
COPY (FROM costs ORDER BY sample,one_way_bp)
TO 'data/research/experiments/lopez-drift-costs/scenarios.csv' (HEADER);
