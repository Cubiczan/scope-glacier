-- 30-day price level, volatility, and returns. Same question as
-- src/aws/athena_views/energy_price_dashboard.sql.
-- Database qualifier is substituted before execution.

WITH recent AS (
    SELECT
        commodity_code,
        commodity_name,
        price_date,
        price_value
    FROM {db}.price_series
    WHERE price_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
),
stats AS (
    SELECT
        commodity_code,
        MAX(price_date) AS latest_date,
        ROUND(AVG(price_value), 2) AS avg_price_30d,
        ROUND(stddev_samp(price_value), 2) AS std_dev_30d
    FROM recent
    GROUP BY commodity_code
),
ranked AS (
    SELECT
        commodity_code,
        commodity_name,
        price_date,
        price_value,
        LAG(price_value, 1) OVER (PARTITION BY commodity_code ORDER BY price_date) AS prev_price,
        LAG(price_value, 20) OVER (PARTITION BY commodity_code ORDER BY price_date) AS price_20d_ago,
        ROW_NUMBER() OVER (PARTITION BY commodity_code ORDER BY price_date DESC) AS rn
    FROM recent
)
SELECT
    stats.commodity_code,
    COALESCE(ec.name, ranked.commodity_name, stats.commodity_code) AS commodity_name,
    COALESCE(ec.energy_type, 'Unknown') AS energy_type,
    ranked.price_value AS latest_price,
    COALESCE(ec.unit, 'USD/barrel') AS unit,
    stats.avg_price_30d,
    stats.std_dev_30d,
    CASE
        WHEN stats.avg_price_30d > 0 AND stats.std_dev_30d IS NOT NULL
            THEN ROUND(stats.std_dev_30d / stats.avg_price_30d * 100, 2)
        ELSE 0
    END AS coefficient_of_variation_pct,
    CASE
        WHEN ranked.prev_price > 0
            THEN ROUND((ranked.price_value - ranked.prev_price) / ranked.prev_price * 100, 2)
        ELSE NULL
    END AS daily_return_pct,
    CASE
        WHEN ranked.price_20d_ago > 0
            THEN ROUND((ranked.price_value - ranked.price_20d_ago) / ranked.price_20d_ago * 100, 2)
        ELSE NULL
    END AS return_20d_pct,
    stats.latest_date
FROM stats
JOIN ranked
    ON ranked.commodity_code = stats.commodity_code
   AND ranked.rn = 1
LEFT JOIN {db}.energy_commodities ec
    ON ec.code = stats.commodity_code
