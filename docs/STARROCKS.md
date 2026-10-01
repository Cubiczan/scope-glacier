# StarRocks spike — interactive SQL on the Scope.Glacier lake

StarRocks is an optional query layer for the energy-market tables Athena already reads. The lake stays in S3 as Apache Iceberg, registered in the AWS Glue database `scope_glacier`. Athena, Glue ETL, and Step Functions stay as they are.

This spike is a laptop-sized FE/BE cluster plus the catalog SQL that points StarRocks at that same Glue database. It is not a migration off Athena.

## When to use which engine

| Workload | Use |
|---|---|
| Glue ETL (`src/aws/glue_scripts/`), the Step Functions pipeline, and the checked-in Athena views | **Athena.** Those jobs already submit SQL to the Athena workgroup `scope-glacier-wg` and write results to the queries bucket. |
| Occasional wide scans, or any path that should stay serverless | **Athena.** You pay per terabyte scanned and there is no cluster to run. |
| Repeated dashboard SQL, or an agent issuing many small analytical queries against the same lake | **StarRocks.** The FE plans MySQL-protocol queries (port 9030); BEs scan Iceberg in parallel and keep a local data cache, which is what makes a second and third identical question cheap. |
| Proving the demo on a machine without AWS credentials | **StarRocks fixture database** `scope_glacier_demo`. Synthetic rows in native tables, same column names as Glue. |

Both engines answer the same product questions:

| Question | Athena view | StarRocks question id |
|---|---|---|
| 30-day price level, volatility, daily and 20-day return | `scope_glacier.energy_price_dashboard_v` | `price_dashboard` |
| Implied balance, inventory cover, drawdown risk, balance vs prior 4 weeks | `scope_glacier.supply_demand_fundamentals_v` | `supply_demand` |
| Pipeline and refinery disruption and offline capacity | `scope_glacier.infrastructure_disruption_v` | `infrastructure_disruption` |
| Latest composite Glacier signal per commodity | `scope_glacier.glacier_signals` (base table; no Athena view) | `latest_signal` |
| One-commodity balance for an agent (WTI, last 90 days, `LIMIT 12`) | same fundamentals view, narrowed | `wti_balance` |

`wti_balance` is the shape to prefer for an agent loop: equality predicate on `commodity_code`, a bounded `date` range, a `LIMIT`, and no DDL. That is the query most likely to prune Iceberg metadata and to sit in the BE data cache when many sessions ask it at once.

### Dialect notes

The StarRocks SQL is the same question in MySQL-style syntax.

- Athena `DATE_ADD('DAY', -30, CURRENT_DATE)` is `DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)` on StarRocks.
- The Glue column `date` is a reserved word on StarRocks, so the spike quotes it as `` `date` ``.
- Population vs sample deviation: the spike uses `stddev_samp`.
- The Athena disruption view selects `refineries.offline_bpd`. That column is not in the Glue table (`terraform/main.tf` stores `throughput_bpd` and `utilization_pct`). The StarRocks query derives offline barrels from capacity and throughput, and treats `Shutdown` / `Maintenance` / `Reduced Flow` / `Force Majeure` the same way the view's `CASE` expressions do.
- Returns are taken from the latest row per commodity inside the 30-day window. That matches the view header. The checked-in Athena view references a `latest_price` column the `returns` CTE does not project; this spike does not change that file.

### Cost shape

Athena in the README estimate is about $5 for 100 queries, because each query scans S3. StarRocks replaces that per-query charge with the cost of keeping FE/BE (or a StarRocks Cloud warehouse) running. The local Compose file costs nothing beyond the machine it runs on. An always-on EKS or StarRocks Cloud deployment is extra and is not part of the ~$9.50 serverless estimate.

Use Athena while query volume is low. Revisit StarRocks when agents or dashboards repeat the same lake questions often enough that cluster time is cheaper than scanned terabytes, or when p95 latency and concurrency matter.

## Catalog and table mapping

Primary path: one external Iceberg catalog over the existing Glue database. StarRocks reads the current Iceberg snapshot. It does not load a copy into native storage.

| Glue database.table | S3 prefix (warehouse bucket) | StarRocks name |
|---|---|---|
| `scope_glacier.price_series` | `s3://scope-glacier-warehouse-<env>/price_series/` | `scope_glacier_iceberg.scope_glacier.price_series` |
| `scope_glacier.supply_demand_balance` | `.../supply_demand_balance/` | `scope_glacier_iceberg.scope_glacier.supply_demand_balance` |
| `scope_glacier.pipelines` | `.../pipelines/` | `scope_glacier_iceberg.scope_glacier.pipelines` |
| `scope_glacier.refineries` | `.../refineries/` | `scope_glacier_iceberg.scope_glacier.refineries` |
| `scope_glacier.glacier_signals` | `.../glacier_signals/` | `scope_glacier_iceberg.scope_glacier.glacier_signals` |
| `scope_glacier.energy_commodities` | `.../energy_commodities/` | `scope_glacier_iceberg.scope_glacier.energy_commodities` |

`<env>` is the Terraform `environment` variable (`dev` by default). The Glue database name is Terraform `glue_database` (`scope_glacier` by default). Athena views `energy_price_dashboard_v`, `supply_demand_fundamentals_v`, and `infrastructure_disruption_v` stay in Glue; the Compose bootstrap creates views with those names only inside the local fixture database.

The Glue tables are Iceberg v2. Partition specs are not declared in Terraform today, so a date predicate is still the right SQL shape, and it will prune manifests if a later change partitions `price_series` by `price_date` or `supply_demand_balance` by `date`.

### Secondary path: native fixture tables

`scope_glacier_demo` holds DUPLICATE KEY tables with `replication_num = 1` and synthetic rows (about 21 daily prices for WTI, Brent, Henry Hub, RBOB, and heating oil, plus weekly balances, pipelines, refineries, and signals). Numbers are invented so the demo has a spread of drawdown risks and disruption statuses. They are not EIA publications.

Do not `CREATE TABLE AS SELECT` from the Iceberg catalog into these native tables for the product path. That would fork the lake. The fixture exists so `scripts/starrocks_query.py` can print latencies when Glue is unreachable.

## Deploy options

### 1. Docker Compose (this repo)

Shared-nothing, one FE and one BE, images `starrocks/fe-ubuntu:3.3-latest` and `starrocks/be-ubuntu:3.3-latest`. SQL port **9030**, FE HTTP **8030**, BE HTTP **8040**. Give Docker at least 6 GB of RAM; the FE is a JVM and the BE is the scan executor.

```bash
docker compose -f docker-compose.starrocks.yml up -d
docker compose -f docker-compose.starrocks.yml logs -f starrocks-init
# last line should be: bootstrap complete

python scripts/starrocks_query.py
python scripts/starrocks_agent_query.py wti_balance
```

`scripts/starrocks_demo.sh` runs those steps together.

The init container registers `starrocks-be:9050`, creates `scope_glacier_demo`, loads `starrocks/init/02_fixture_seed.sql` when `price_series` is empty, and creates the three Athena-equivalent views from `starrocks/sql/`. Set `STARROCKS_RESEED=1` on the init service to truncate and load again.

Interactive client (empty root password, same as the StarRocks images):

```bash
mysql -h 127.0.0.1 -P 9030 -u root
USE scope_glacier_demo;
SELECT * FROM energy_price_dashboard_v;
```

### Attach the real Glue catalog

The catalog statement is `starrocks/init/01_iceberg_catalog.sql`. Placeholders are filled from the environment. Nothing in the file is a live key.

IAM for a read-only spike (the Athena workgroup policy can stay untouched):

- `glue:GetDatabase`, `glue:GetDatabases`, `glue:GetTable`, `glue:GetTables`, `glue:GetPartition`, `glue:GetPartitions` on database `scope_glacier`
- `s3:GetObject`, `s3:ListBucket` on the warehouse bucket (`scope-glacier-warehouse-<env>`)

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
export GLUE_DATABASE=scope_glacier

# either re-run init (it skips the catalog when the key is empty):
docker compose -f docker-compose.starrocks.yml up -d --force-recreate starrocks-init

# or register from the host after the FE is up:
python scripts/starrocks_query.py --register-iceberg --source iceberg
```

`--source auto` (the default) uses `scope_glacier_iceberg.<GLUE_DATABASE>` when that catalog answers `SHOW DATABASES`, and otherwise uses `scope_glacier_demo`.

On EKS the catalog should use the node or IRSA role instead of access keys:

```sql
CREATE EXTERNAL CATALOG scope_glacier_iceberg
PROPERTIES (
    "type" = "iceberg",
    "iceberg.catalog.type" = "glue",
    "aws.glue.use_instance_profile" = "true",
    "aws.glue.iam_role_arn" = "arn:aws:iam::<account-id>:role/scope-glacier-starrocks",
    "aws.glue.region" = "us-east-1",
    "aws.s3.use_instance_profile" = "true",
    "aws.s3.iam_role_arn" = "arn:aws:iam::<account-id>:role/scope-glacier-starrocks",
    "aws.s3.region" = "us-east-1"
);
```

### 2. AWS (EKS)

Run the StarRocks Kubernetes operator (Helm chart `kube-starrocks`) with one FE and at least two BEs in the same region as the warehouse (`us-east-1` by default). Attach an IRSA role with the Glue and S3 reads above. Apply the instance-profile catalog statement. BEs need outbound HTTPS to Glue and S3. Leave the Athena workgroup, Glue ETL jobs, and Lambda environment variables in place. Shared-data mode (FE + compute nodes + object storage) is a later sizing choice; this spike's Compose file is shared-nothing FE/BE so external Iceberg scans run on the BE.

### 3. StarRocks Cloud

A CelerData / StarRocks Cloud warehouse in the same region can run the same `CREATE EXTERNAL CATALOG` statement against Glue. The client protocol is still MySQL on port 9030, so `scripts/starrocks_query.py` only needs `STARROCKS_HOST` / `STARROCKS_PORT` / `STARROCKS_USER` / `STARROCKS_PASSWORD`. Network path: the warehouse must read the Iceberg warehouse bucket. Still no copy into native tables.

## Query helper and agent example

`scripts/starrocks_query.py` opens a MySQL-protocol connection, runs the question SQL, and prints row counts and latency.

```bash
pip install pymysql          # already listed in requirements.txt
python scripts/starrocks_query.py --list
python scripts/starrocks_query.py --source fixture
python scripts/starrocks_query.py --dry-run    # render SQL, do not connect
```

`scripts/starrocks_agent_query.py` is the agent-facing wrapper. It runs one question (default `wti_balance`) and prints a JSON-RPC `tools/call` result. The tool descriptor is `starrocks/mcp/query_energy_lake.tool.json`. This is a CLI with that shape, not a hosted MCP server.

```bash
python scripts/starrocks_agent_query.py --dry-run
python scripts/starrocks_agent_query.py wti_balance
```

Environment (see `.env.example`):

| Variable | Default | Role |
|---|---|---|
| `STARROCKS_HOST` | `127.0.0.1` | FE hostname |
| `STARROCKS_PORT` | `9030` | MySQL protocol |
| `STARROCKS_USER` | `root` | Demo user |
| `STARROCKS_PASSWORD` | empty | Demo password |
| `STARROCKS_SOURCE` | `auto` | `auto`, `iceberg`, or `fixture` |
| `GLUE_DATABASE` | `scope_glacier` | Database inside the external catalog |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` | unset | Catalog registration only |

## Troubleshooting

- Init never prints `bootstrap complete`: `docker compose -f docker-compose.starrocks.yml logs starrocks-fe starrocks-be starrocks-init`. The FE healthcheck waits until `SHOW FRONTENDS` reports `Alive: true`.
- `SHOW BACKENDS` stays `Alive: false`: the BE must resolve `starrocks-fe` and the FE must reach `starrocks-be:9050` on the Compose network. Both services set `--host_type FQDN`.
- Catalog registration fails: confirm the IAM identity can `GetTable` on `scope_glacier` and `GetObject` on the warehouse bucket, and that `AWS_REGION` matches the bucket. Fixture queries still run with `--source fixture`.
- Credentials with quotes, backslashes, or newlines are rejected by the bootstrap and by `--register-iceberg` so they are not interpolated into SQL.
