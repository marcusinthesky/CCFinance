-- Run in DuckDB from the project root with the frozen research inputs restored.
CREATE TEMP VIEW eligible AS
SELECT * FROM 'data/research/coverage/panel.parquet'
WHERE in_universe AND year BETWEEN 2017 AND 2025;

SELECT year, size_band, basis, count(*) AS eligible,
       countif(usable >= 50) AS usable_50, countif(focused >= 50) AS focused_50
FROM eligible GROUP BY GROUPING SETS ((year), (size_band), (basis), ())
ORDER BY GROUPING_ID(year, size_band, basis), year, size_band, basis;

SELECT year(captured) AS capture_year, date_status, count(*) AS records
FROM 'data/processed/articles/articles.parquet' GROUP BY ALL ORDER BY 1, 2;

SELECT host, count(*) AS staged, countif(usable) AS usable
FROM 'data/processed/articles/articles.parquet' GROUP BY host ORDER BY staged DESC;

SELECT countif(usable AND lag_days BETWEEN 2 AND 7) AS delayed, countif(usable) AS usable
FROM 'data/processed/articles/articles.parquet';

SELECT count(*) AS repeated_urls, countif(versions > 1) AS multiple_text_hashes
FROM (SELECT metadata.normalized_url, count(DISTINCT metadata.text_xxhash64) AS versions
      FROM 'data/raw/fine-news/**/*.parquet'
      WHERE metadata.normalized_url IS NOT NULL AND metadata.text_xxhash64 IS NOT NULL
      GROUP BY 1 HAVING count(*) > 1);

SELECT host, countif(date_status = 'archival') AS late
FROM 'data/processed/articles/articles.parquet' WHERE year(captured) = 2017
GROUP BY host ORDER BY late DESC;
