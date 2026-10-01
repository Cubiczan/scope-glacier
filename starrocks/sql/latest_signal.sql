-- Latest composite Glacier signal per commodity.
-- Scores follow the product weights stored on the row
-- (supply/demand 0.30, momentum 0.25, geopolitical 0.25, seasonal 0.20).

SELECT
    signal_id,
    commodity_code,
    generated_at,
    supply_demand_score,
    price_momentum_score,
    geopolitical_score,
    seasonal_score,
    glacier_score,
    signal_rating,
    confidence_score,
    ai_analysis
FROM (
    SELECT
        signal_id,
        commodity_code,
        generated_at,
        supply_demand_score,
        price_momentum_score,
        geopolitical_score,
        seasonal_score,
        glacier_score,
        signal_rating,
        confidence_score,
        ai_analysis,
        ROW_NUMBER() OVER (
            PARTITION BY commodity_code
            ORDER BY generated_at DESC
        ) AS rn
    FROM {db}.glacier_signals
) ranked
WHERE rn = 1
