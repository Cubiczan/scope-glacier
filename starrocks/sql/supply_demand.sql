-- Implied balance, inventory cover, drawdown risk, and the gap versus the
-- prior 28 days. Same question as src/aws/athena_views/supply_demand_fundamentals.sql.
-- The prior-window average is a range join so daily and weekly snapshots both
-- match the Athena date predicate.

WITH base AS (
    SELECT
        commodity_code,
        period,
        `date`,
        production_mbd,
        consumption_mbd,
        imports_mbd,
        exports_mbd,
        production_mbd - consumption_mbd + imports_mbd - exports_mbd AS implied_balance_mbd,
        inventory_mmbl,
        inventory_change_mmbl,
        spare_capacity_mbd,
        utilization_pct
    FROM {db}.supply_demand_balance
),
prior AS (
    SELECT
        current_row.commodity_code,
        current_row.`date`,
        AVG(earlier.implied_balance_mbd) AS avg_balance_prior_4w
    FROM base current_row
    LEFT JOIN base earlier
        ON earlier.commodity_code = current_row.commodity_code
       AND earlier.`date` >= DATE_SUB(current_row.`date`, INTERVAL 28 DAY)
       AND earlier.`date` < current_row.`date`
    GROUP BY current_row.commodity_code, current_row.`date`
)
SELECT
    base.commodity_code,
    COALESCE(ec.name, base.commodity_code) AS commodity_name,
    base.period,
    base.`date`,
    base.production_mbd,
    base.consumption_mbd,
    base.imports_mbd,
    base.exports_mbd,
    base.implied_balance_mbd,
    base.inventory_mmbl,
    base.inventory_change_mmbl,
    CASE
        WHEN base.consumption_mbd > 0 THEN ROUND(base.inventory_mmbl / base.consumption_mbd, 1)
        ELSE 0
    END AS inventory_coverage_days,
    CASE
        WHEN base.consumption_mbd <= 0 THEN 'Comfortable'
        WHEN base.inventory_mmbl / base.consumption_mbd < 20 THEN 'Critical'
        WHEN base.inventory_mmbl / base.consumption_mbd < 30 THEN 'Low'
        WHEN base.inventory_mmbl / base.consumption_mbd < 50 THEN 'Adequate'
        ELSE 'Comfortable'
    END AS drawdown_risk,
    base.spare_capacity_mbd,
    base.utilization_pct,
    ROUND(base.implied_balance_mbd - COALESCE(prior.avg_balance_prior_4w, 0), 2) AS balance_vs_4w_avg_mbd
FROM base
LEFT JOIN prior
    ON prior.commodity_code = base.commodity_code
   AND prior.`date` = base.`date`
LEFT JOIN {db}.energy_commodities ec
    ON ec.code = base.commodity_code
