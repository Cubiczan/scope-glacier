-- Agent-shaped read: one commodity, a bounded date range, and a LIMIT.
-- Equality on commodity_code plus the date predicate is what Iceberg
-- metadata pruning and the BE data cache can reuse across concurrent sessions.
-- No DDL, no catalog switches, no correlated scalar subquery.

SELECT
    commodity_code,
    `date`,
    period,
    production_mbd,
    consumption_mbd,
    imports_mbd,
    exports_mbd,
    production_mbd - consumption_mbd + imports_mbd - exports_mbd AS implied_balance_mbd,
    CASE
        WHEN consumption_mbd > 0 THEN ROUND(inventory_mmbl / consumption_mbd, 1)
        ELSE 0
    END AS inventory_coverage_days,
    spare_capacity_mbd,
    utilization_pct
FROM {db}.supply_demand_balance
WHERE commodity_code = 'WTI'
  AND `date` >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
ORDER BY `date` DESC
LIMIT 12
