-- Native tables used only when the Glue Iceberg catalog is not attached.
-- Column names match terraform/main.tf. Key columns are ordered first so
-- StarRocks can use them as a DUPLICATE KEY. replication_num = 1 suits one BE.

CREATE DATABASE IF NOT EXISTS scope_glacier_demo;
USE scope_glacier_demo;

CREATE TABLE IF NOT EXISTS energy_commodities (
    code VARCHAR(32),
    commodity_id VARCHAR(64),
    name VARCHAR(128),
    energy_type VARCHAR(64),
    current_price DOUBLE,
    unit VARCHAR(64),
    eia_series_id VARCHAR(128),
    updated_at DATETIME
)
DUPLICATE KEY(code)
DISTRIBUTED BY HASH(code) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS price_series (
    commodity_code VARCHAR(32),
    price_date DATE,
    commodity_name VARCHAR(128),
    price_value DOUBLE,
    source VARCHAR(64),
    ingested_at DATETIME
)
DUPLICATE KEY(commodity_code, price_date)
DISTRIBUTED BY HASH(commodity_code) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS supply_demand_balance (
    commodity_code VARCHAR(32),
    `date` DATE,
    period VARCHAR(32),
    production_mbd DOUBLE,
    consumption_mbd DOUBLE,
    imports_mbd DOUBLE,
    exports_mbd DOUBLE,
    inventory_mmbl DOUBLE,
    inventory_change_mmbl DOUBLE,
    spare_capacity_mbd DOUBLE,
    utilization_pct DOUBLE
)
DUPLICATE KEY(commodity_code, date)
DISTRIBUTED BY HASH(commodity_code) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id VARCHAR(64),
    name VARCHAR(128),
    commodity VARCHAR(64),
    origin VARCHAR(128),
    destination VARCHAR(128),
    capacity_bpd DOUBLE,
    current_flow_bpd DOUBLE,
    status VARCHAR(64),
    length_miles DOUBLE,
    countries_crossed VARCHAR(128)
)
DUPLICATE KEY(pipeline_id)
DISTRIBUTED BY HASH(pipeline_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS refineries (
    refinery_id VARCHAR(64),
    name VARCHAR(128),
    region VARCHAR(64),
    country VARCHAR(64),
    capacity_bpd DOUBLE,
    utilization_pct DOUBLE,
    status VARCHAR(64),
    crude_type VARCHAR(64),
    throughput_bpd DOUBLE
)
DUPLICATE KEY(refinery_id)
DISTRIBUTED BY HASH(refinery_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

CREATE TABLE IF NOT EXISTS glacier_signals (
    commodity_code VARCHAR(32),
    generated_at DATETIME,
    signal_id VARCHAR(64),
    supply_demand_score DOUBLE,
    price_momentum_score DOUBLE,
    geopolitical_score DOUBLE,
    seasonal_score DOUBLE,
    glacier_score DOUBLE,
    signal_rating VARCHAR(32),
    ai_analysis VARCHAR(1024),
    confidence_score DOUBLE,
    data_sources VARCHAR(256)
)
DUPLICATE KEY(commodity_code, generated_at)
DISTRIBUTED BY HASH(commodity_code) BUCKETS 1
PROPERTIES ("replication_num" = "1");
