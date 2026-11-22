-- Screen opportunities without changing the fixed sample or reading returns.
SET threads = 3;
SET memory_limit = '2GB';
CREATE TEMP TABLE calendar AS
SELECT s.session, p.close_at AS previous_close, s.cutoff_at
FROM 'data/processed/experiments/lopez-lira-tang-events/sessions.parquet' s
JOIN 'data/processed/experiments/lopez-lira-tang-events/sessions.parquet' p
  ON p.session = s.previous_session
WHERE s.session BETWEEN DATE '2021-10-01' AND DATE '2024-05-31';

CREATE TEMP TABLE original AS
SELECT DISTINCT session, cik
FROM 'data/processed/experiments/lopez-lira-tang-sample/sample.parquet';
CREATE TEMP TABLE candidates AS
SELECT a.id, a.host, c.session, l.cik
FROM 'data/processed/articles/articles.parquet' a
JOIN calendar c ON a.captured > c.previous_close AND a.captured <= c.cutoff_at
  AND a.published BETWEEN (c.previous_close::DATE - 1) AND (c.cutoff_at::DATE + 1)
JOIN 'data/processed/company-links/articles/*.parquet' l USING (id)
SEMI JOIN original u ON u.cik = l.cik
WHERE a.usable AND a.extraction_status='ok' AND a.text_length>0
  AND l.n_mentions>=3 AND l.first_offset_share<=1
  AND l.relevance_substantive>=0 AND l.link_score>=0.5
  AND a.host NOT IN ('business-standard.com', 'lifestyle.livemint.com');

CREATE TEMP TABLE daily AS
WITH base AS (
    SELECT c.session, count(o.cik) AS base_firms
    FROM calendar c LEFT JOIN original o USING (session) GROUP BY c.session
)
SELECT c.host, c.session, b.base_firms, count(DISTINCT c.cik) AS candidate_firms,
       count(DISTINCT c.cik) FILTER (WHERE o.cik IS NULL) AS extra_firms
FROM candidates c JOIN base b USING (session) LEFT JOIN original o USING (session, cik)
GROUP BY c.host, c.session, b.base_firms;
COPY (SELECT * FROM daily ORDER BY host,session)
TO 'data/research/experiments/lopez-publisher-support/host_sessions.csv' (HEADER);
COPY (
    SELECT host, count(*) AS candidate_sessions, sum(extra_firms) AS extra_firm_sessions,
           count_if(base_firms < 4 AND base_firms+extra_firms>=4) AS crossing_four,
           count_if(base_firms BETWEEN 1 AND 3 AND base_firms+extra_firms>=4) AS one_to_three_crossing
    FROM daily GROUP BY host ORDER BY crossing_four DESC,extra_firm_sessions DESC,host
) TO 'data/research/experiments/lopez-publisher-support/publishers.csv' (HEADER);

CREATE TEMP TABLE missing AS
SELECT id, captured FROM 'data/processed/experiments/lopez-lira-tang-events/timestamps.parquet'
WHERE host='business-standard.com' AND timing_status='no_first_publication';
CREATE TEMP TABLE markers AS
SELECT n.id, n.metadata.url AS url, m.captured,
       regexp_extract(n.text, '(?i)first published[^\n]{0,100}') AS first_marker,
       regexp_extract(n.text, '(?i)(?:last updated|updated on)[^\n]{0,100}') AS update_marker,
       regexp_extract(n.text, '(?i)First Published:\s*([a-z]{3},\s+[a-z]+\s+\d{1,2}\s+20\d{2}\.\s+\d{1,2}:\d{2})\s+IST\b', 1) AS old_clock
FROM 'data/raw/fine-news/**/*.parquet' n JOIN missing m USING (id);
CREATE TEMP TABLE parsed AS
WITH clocks AS (
  SELECT *, try_strptime(old_clock, '%a, %B %d %Y. %H:%M') AS local_clock FROM markers
)
SELECT *, timezone('UTC', timezone('Asia/Kolkata', local_clock)) AS first_utc
FROM clocks WHERE lower(strftime(local_clock,'%a'))=lower(left(old_clock,3));
COPY (
  SELECT m.id,m.url,m.first_marker,m.update_marker,p.first_utc
  FROM markers m LEFT JOIN parsed p USING(id) ORDER BY hash(m.id),m.id LIMIT 512
) TO 'data/research/experiments/lopez-publisher-support/timestamp_audit.csv' (HEADER);
CREATE TEMP TABLE timed AS
SELECT p.id,p.first_utc,p.captured,c.session
FROM parsed p JOIN calendar c ON p.first_utc>c.previous_close AND p.first_utc<c.cutoff_at
WHERE p.captured BETWEEN p.first_utc AND c.cutoff_at;
COPY (
  SELECT t.*,l.cik, o.cik IS NULL AS extra_firm_session
  FROM timed t JOIN 'data/processed/company-links/articles/*.parquet' l USING(id)
  SEMI JOIN original u ON u.cik=l.cik
  LEFT JOIN original o ON o.session=t.session AND o.cik=l.cik
  JOIN 'data/processed/articles/articles.parquet' a ON a.id=t.id
  WHERE a.extraction_status='ok' AND a.text_length>0 AND l.n_mentions>=3 AND l.first_offset_share<=1
    AND l.relevance_substantive>=0 AND l.link_score>=0.5
  ORDER BY session,t.id,l.cik
) TO 'data/research/experiments/lopez-publisher-support/recovered_links.csv' (HEADER);
COPY (
  SELECT (SELECT count(*) FROM missing) AS missing_first_time,
         (SELECT count(*) FROM parsed) AS recovered_first_times,
         (SELECT count(*) FROM timed) AS recovered_overnight_evaluation_dates
) TO 'data/research/experiments/lopez-publisher-support/recovery.csv' (HEADER);
-- Trace a deterministic sample for the highest-ranked prospective hosts.
CREATE TEMP TABLE inspect_ids AS
WITH top_hosts AS (
  SELECT host FROM 'data/research/experiments/lopez-publisher-support/publishers.csv'
  ORDER BY crossing_four DESC, extra_firm_sessions DESC,host LIMIT 5
)
SELECT DISTINCT host,id FROM (SELECT DISTINCT host,id FROM candidates SEMI JOIN top_hosts USING(host))
QUALIFY row_number() OVER(PARTITION BY host ORDER BY hash(id),id)<=32;
COPY (
  SELECT i.host,i.id,n.metadata.url AS url,
    regexp_extract(n.text, '(?i)\b(?:first published|originally published|published (?:at|on))[^\n]{0,100}') AS publication_marker,
    regexp_extract(n.text, '(?i)\b(?:last updated|updated (?:at|on))[^\n]{0,100}') AS update_marker
  FROM 'data/raw/fine-news/**/*.parquet' n JOIN inspect_ids i USING(id)
  ORDER BY i.host,i.id
) TO 'data/research/experiments/lopez-publisher-support/prospective_clock_audit.csv' (HEADER);
