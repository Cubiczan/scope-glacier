-- Synthetic rows for scope_glacier_demo. Not EIA data.
-- Prices are a 21-day ramp so the 30-day dashboard and LAG(..., 20) both return values.
-- Balances span four weekly observations so the prior-4-week average is defined.

USE scope_glacier_demo;

INSERT INTO energy_commodities (
    code, commodity_id, name, energy_type, current_price, unit, eia_series_id, updated_at
) VALUES
    ('WTI', 'NRG_WTI', 'West Texas Intermediate', 'Crude Oil', 78.10, 'USD/barrel', 'PET.RWTC.D', NOW()),
    ('BRENT', 'NRG_BRENT', 'Brent Crude', 'Crude Oil', 82.80, 'USD/barrel', 'PET.RBRTE.D', NOW()),
    ('HH', 'NRG_HH', 'Henry Hub Natural Gas', 'Natural Gas', 3.20, 'USD/MMBtu', 'NG.RNGWHHD.D', NOW()),
    ('RBOB', 'NRG_RBOB', 'RBOB Gasoline', 'Gasoline', 2.34, 'USD/gallon', 'PET.EER_EPMRU_PF4_YCG_DPG.D', NOW()),
    ('HO', 'NRG_HO', 'No. 2 Heating Oil', 'Heating Oil', 2.48, 'USD/gallon', 'PET.EER_EPD2F_PF4_Yhou_DPG.D', NOW()),
    ('URANIUM', 'NRG_URANIUM', 'Uranium U3O8', 'Nuclear', 0.0, 'USD/lb', '', NOW());

INSERT INTO price_series (
    commodity_code, price_date, commodity_name, price_value, source, ingested_at
)
SELECT
    series.code,
    DATE_SUB(CURRENT_DATE(), INTERVAL offsets.offset_day DAY),
    series.name,
    ROUND(series.base_price + series.daily_step * (21 - offsets.offset_day), 4),
    'fixture',
    NOW()
FROM (
    SELECT 'WTI' AS code, 'West Texas Intermediate' AS name, 74.50 AS base_price, 0.18 AS daily_step
    UNION ALL SELECT 'BRENT', 'Brent Crude', 78.80, 0.20
    UNION ALL SELECT 'HH', 'Henry Hub Natural Gas', 2.80, 0.02
    UNION ALL SELECT 'RBOB', 'RBOB Gasoline', 2.10, 0.012
    UNION ALL SELECT 'HO', 'No. 2 Heating Oil', 2.28, 0.01
) series
JOIN (
    SELECT 1 AS offset_day UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
    UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8
    UNION ALL SELECT 9 UNION ALL SELECT 10 UNION ALL SELECT 11 UNION ALL SELECT 12
    UNION ALL SELECT 13 UNION ALL SELECT 14 UNION ALL SELECT 15 UNION ALL SELECT 16
    UNION ALL SELECT 17 UNION ALL SELECT 18 UNION ALL SELECT 19 UNION ALL SELECT 20
    UNION ALL SELECT 21
) offsets ON TRUE;

INSERT INTO supply_demand_balance (
    commodity_code, `date`, period, production_mbd, consumption_mbd, imports_mbd, exports_mbd,
    inventory_mmbl, inventory_change_mmbl, spare_capacity_mbd, utilization_pct
)
SELECT
    series.commodity_code,
    DATE_SUB(CURRENT_DATE(), INTERVAL offsets.weeks * 7 DAY),
    'weekly',
    ROUND(series.production_mbd + (3 - offsets.weeks) * 0.05, 3),
    series.consumption_mbd,
    series.imports_mbd,
    series.exports_mbd,
    ROUND(series.inventory_mmbl - (3 - offsets.weeks) * series.weekly_draw_mmbl, 3),
    ROUND(-series.weekly_draw_mmbl, 3),
    series.spare_capacity_mbd,
    series.utilization_pct
FROM (
    SELECT 'WTI' AS commodity_code, 13.20 AS production_mbd, 20.40 AS consumption_mbd,
           6.80 AS imports_mbd, 4.10 AS exports_mbd, 428.0 AS inventory_mmbl,
           1.8 AS weekly_draw_mmbl, 2.40 AS spare_capacity_mbd, 92.0 AS utilization_pct
    UNION ALL SELECT 'BRENT', 12.40, 14.10, 1.20, 8.60, 610.0, 0.4, 3.10, 88.0
    UNION ALL SELECT 'HH', 104.0, 98.5, 7.5, 12.0, 3450.0, 12.0, 8.0, 86.0
    UNION ALL SELECT 'RBOB', 8.60, 9.40, 0.40, 0.20, 180.0, 3.0, 0.60, 94.0
) series
JOIN (
    SELECT 0 AS weeks UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
) offsets ON TRUE;

INSERT INTO pipelines (
    pipeline_id, name, commodity, origin, destination, capacity_bpd, current_flow_bpd,
    status, length_miles, countries_crossed
) VALUES
    ('PIPE_Colonial', 'Colonial Pipeline', 'Refined products', 'Houston, TX', 'New York Harbor',
     2500000, 2100000, 'Operational', 5500, 'US'),
    ('PIPE_Keystone', 'Keystone', 'Crude Oil', 'Hardisty, AB', 'Cushing, OK',
     590000, 520000, 'Operational', 2687, 'CA,US'),
    ('PIPE_Druzhba', 'Druzhba', 'Crude Oil', 'Almetyevsk', 'Schwedt',
     1400000, 700000, 'Reduced Flow', 2500, 'RU,BY,PL,DE'),
    ('PIPE_Demo_Spur', 'Demo Spur Line', 'Crude Oil', 'Sample Origin', 'Sample Dest',
     180000, 0, 'Shutdown', 40, 'US');

INSERT INTO refineries (
    refinery_id, name, region, country, capacity_bpd, utilization_pct, status, crude_type, throughput_bpd
) VALUES
    ('REF_Baytown_Gulf_Coast', 'Baytown', 'Gulf Coast', 'United States',
     560000, 88.0, 'Operating', 'Light Sweet', 492800),
    ('REF_Port_Arthur_Gulf_Coast', 'Port Arthur', 'Gulf Coast', 'United States',
     630000, 40.0, 'Maintenance', 'Medium Sour', 252000),
    ('REF_Rotterdam_ARA', 'Rotterdam', 'ARA', 'Netherlands',
     400000, 91.0, 'Operating', 'Light Sweet', 364000),
    ('REF_Demo_Works_Gulf_Coast', 'Demo Works', 'Gulf Coast', 'United States',
     120000, 0.0, 'Shutdown', 'Heavy Sour', 0);

INSERT INTO glacier_signals (
    commodity_code, generated_at, signal_id, supply_demand_score, price_momentum_score,
    geopolitical_score, seasonal_score, glacier_score, signal_rating, ai_analysis,
    confidence_score, data_sources
) VALUES
    ('WTI', NOW(), 'WTI_fixture', 72, 68, 65, 55, 65.85, 'Buy',
     'Fixture signal. Tight cover and positive momentum.', 0.72, 'fixture'),
    ('BRENT', NOW(), 'BRENT_fixture', 70, 66, 70, 50, 65.00, 'Buy',
     'Fixture signal. Similar crude balance to WTI.', 0.70, 'fixture'),
    ('HH', NOW(), 'HH_fixture', 45, 40, 35, 60, 44.25, 'Hold',
     'Fixture signal. Gas balance inside the hold band.', 0.64, 'fixture'),
    ('RBOB', NOW(), 'RBOB_fixture', 80, 75, 60, 70, 71.75, 'Buy',
     'Fixture signal. Low product cover.', 0.68, 'fixture'),
    ('HO', NOW(), 'HO_fixture', 30, 35, 40, 25, 32.75, 'Sell',
     'Fixture signal. Soft heating-oil score.', 0.60, 'fixture');
