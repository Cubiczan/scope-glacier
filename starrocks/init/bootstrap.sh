#!/usr/bin/env bash
# Register the BE, load fixture tables, create Athena-equivalent views,
# and optionally register the Glue Iceberg catalog.
# Credentials are read from the environment and are not echoed.

set -euo pipefail

HOST="${STARROCKS_HOST:-starrocks-fe}"
PORT="${STARROCKS_PORT:-9030}"
USER_NAME="${STARROCKS_USER:-root}"
ROOT="/starrocks"
FIXTURE_DB="scope_glacier_demo"

mysql_exec() {
  mysql --protocol=TCP -h "$HOST" -P "$PORT" -u "$USER_NAME" --batch "$@"
}

echo "Waiting for StarRocks FE at ${HOST}:${PORT}"
ready=0
for _ in $(seq 1 60); do
  if mysql_exec -e "SELECT 1" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "FE did not accept connections" >&2
  exit 1
fi

echo "Registering backend starrocks-be:9050"
if ! mysql_exec -e "SHOW BACKENDS\G" | grep -q "starrocks-be"; then
  mysql_exec -e "ALTER SYSTEM ADD BACKEND \"starrocks-be:9050\";"
fi

echo "Waiting for backend Alive"
alive=0
for _ in $(seq 1 60); do
  if mysql_exec -e "SHOW BACKENDS\G" | grep -q "Alive: true"; then
    alive=1
    break
  fi
  sleep 2
done
if [[ "$alive" -ne 1 ]]; then
  echo "Backend did not become Alive" >&2
  exit 1
fi
echo "Backend is alive"

mysql_exec < "${ROOT}/init/02_fixture_tables.sql"

if [[ "${STARROCKS_RESEED:-}" == "1" ]]; then
  echo "Truncating fixture tables"
  for table in price_series supply_demand_balance pipelines refineries glacier_signals energy_commodities; do
    mysql_exec -e "TRUNCATE TABLE ${FIXTURE_DB}.${table}"
  done
fi

count=$(mysql_exec -N -e "SELECT COUNT(*) FROM ${FIXTURE_DB}.price_series")
if [[ "$count" == "0" ]]; then
  echo "Loading fixture seed"
  mysql_exec < "${ROOT}/init/02_fixture_seed.sql"
else
  echo "Fixture seed already present (${count} price rows)"
fi

create_view() {
  local view_name="$1"
  local sql_file="$2"
  local body
  body=$(sed "s/{db}/${FIXTURE_DB}/g" "$sql_file")
  # printf keeps backticks in the SQL (the `date` column) from being expanded.
  {
    printf 'USE %s;\n' "$FIXTURE_DB"
    printf 'DROP VIEW IF EXISTS %s;\n' "$view_name"
    printf 'CREATE VIEW %s AS\n' "$view_name"
    printf '%s\n' "$body"
  } | mysql_exec
}

echo "Creating fixture views"
create_view energy_price_dashboard_v "${ROOT}/sql/price_dashboard.sql"
create_view supply_demand_fundamentals_v "${ROOT}/sql/supply_demand.sql"
create_view infrastructure_disruption_v "${ROOT}/sql/infrastructure_disruption.sql"

echo "fixtures ready"

register_iceberg() {
  if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    echo "Iceberg catalog skipped. Query ${FIXTURE_DB}, or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
    return 0
  fi
  case "${AWS_ACCESS_KEY_ID}${AWS_SECRET_ACCESS_KEY}${AWS_REGION:-}" in
    *\"*|*\\*|*$'\n'*|*$'\r'*)
      echo "AWS credentials contain characters this demo will not embed in SQL" >&2
      return 1
      ;;
  esac
  if mysql_exec -e "SHOW CATALOGS" | grep -q "scope_glacier_iceberg"; then
    echo "Iceberg catalog scope_glacier_iceberg already registered"
    return 0
  fi
  local sql
  sql=$(< "${ROOT}/init/01_iceberg_catalog.sql")
  sql=${sql//\$\{AWS_ACCESS_KEY_ID\}/${AWS_ACCESS_KEY_ID}}
  sql=${sql//\$\{AWS_SECRET_ACCESS_KEY\}/${AWS_SECRET_ACCESS_KEY}}
  sql=${sql//\$\{AWS_REGION\}/${AWS_REGION:-us-east-1}}
  printf '%s\n' "$sql" | mysql_exec
  echo "Iceberg catalog scope_glacier_iceberg registered"
}

register_iceberg
echo "bootstrap complete"
