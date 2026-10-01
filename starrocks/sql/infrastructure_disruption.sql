-- Pipeline and refinery disruption. Same question as
-- src/aws/athena_views/infrastructure_disruption.sql.
-- offline capacity is derived. Glue refineries do not store offline_bpd.
-- is_disrupted is 1 or 0 so the UNION has a stable numeric type.

SELECT
    'Pipeline' AS asset_type,
    pipeline_id AS asset_id,
    name AS asset_name,
    commodity,
    origin,
    destination,
    capacity_bpd,
    current_flow_bpd,
    ROUND(current_flow_bpd / NULLIF(capacity_bpd, 0) * 100, 1) AS utilization_pct,
    status,
    CASE
        WHEN status IN ('Shutdown', 'Reduced Flow', 'Force Majeure') THEN 1
        ELSE 0
    END AS is_disrupted,
    CASE
        WHEN status = 'Shutdown' THEN capacity_bpd
        WHEN status = 'Reduced Flow' THEN capacity_bpd - current_flow_bpd
        WHEN status = 'Force Majeure' THEN capacity_bpd
        ELSE 0
    END AS estimated_offline_bpd,
    CAST(NULL AS VARCHAR(64)) AS region,
    CAST(NULL AS VARCHAR(64)) AS country,
    CAST(NULL AS VARCHAR(64)) AS crude_type,
    length_miles,
    CAST(NULL AS DOUBLE) AS capacity_offline_bpd
FROM {db}.pipelines

UNION ALL

SELECT
    'Refinery' AS asset_type,
    refinery_id AS asset_id,
    name AS asset_name,
    'Crude Oil' AS commodity,
    CAST(NULL AS VARCHAR(128)) AS origin,
    CAST(NULL AS VARCHAR(128)) AS destination,
    capacity_bpd,
    throughput_bpd AS current_flow_bpd,
    utilization_pct,
    status,
    CASE
        WHEN status IN ('Shutdown', 'Maintenance') THEN 1
        ELSE 0
    END AS is_disrupted,
    CASE
        WHEN status = 'Shutdown' THEN capacity_bpd
        WHEN status = 'Maintenance' THEN capacity_bpd * 0.5
        ELSE 0
    END AS estimated_offline_bpd,
    region,
    country,
    crude_type,
    CAST(NULL AS DOUBLE) AS length_miles,
    capacity_bpd - throughput_bpd AS capacity_offline_bpd
FROM {db}.refineries
