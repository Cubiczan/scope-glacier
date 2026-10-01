"""StarRocks spike: SQL shape, catalog template, and the query helper."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import starrocks_query as sr  # noqa: E402

GLUE_TABLES = (
    "price_series",
    "supply_demand_balance",
    "pipelines",
    "refineries",
    "glacier_signals",
    "energy_commodities",
)

ATHENA_VIEWS = (
    "energy_price_dashboard.sql",
    "supply_demand_fundamentals.sql",
    "infrastructure_disruption.sql",
)


def test_athena_views_still_present():
    view_dir = ROOT / "src" / "aws" / "athena_views"
    for name in ATHENA_VIEWS:
        text = (view_dir / name).read_text(encoding="utf-8")
        assert "CREATE OR REPLACE VIEW scope_glacier." in text


def test_question_ids_cover_athena_views():
    ids = [q["id"] for q in sr.QUESTIONS]
    assert ids == [
        "price_dashboard",
        "supply_demand",
        "infrastructure_disruption",
        "latest_signal",
        "wti_balance",
    ]
    views = {q["athena_view"] for q in sr.QUESTIONS}
    assert "scope_glacier.energy_price_dashboard_v" in views
    assert "scope_glacier.supply_demand_fundamentals_v" in views
    assert "scope_glacier.infrastructure_disruption_v" in views


def test_rendered_sql_uses_fixture_or_iceberg_database():
    for question in sr.QUESTIONS:
        for source, glue in (("fixture", "scope_glacier"), ("iceberg", "scope_glacier")):
            database = sr.qualify(source, glue)
            sql = sr.render_sql(question, database, limit=0)
            assert "{db}" not in sql
            assert "DATE_ADD(" not in sql
            assert database in sql
            assert sql.count("(") == sql.count(")")


def test_wti_balance_is_the_narrow_agent_query():
    sql = sr.render_sql(sr.question_by_id("wti_balance"), sr.FIXTURE_DB, limit=500)
    assert "commodity_code = 'WTI'" in sql
    assert "INTERVAL 90 DAY" in sql
    assert sql.strip().endswith("LIMIT 12")


def test_fixture_ddl_mirrors_glue_tables():
    ddl = (ROOT / "starrocks" / "init" / "02_fixture_tables.sql").read_text(encoding="utf-8")
    seed = (ROOT / "starrocks" / "init" / "02_fixture_seed.sql").read_text(encoding="utf-8")
    for table in GLUE_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl
        assert table in seed
    assert ddl.count('"replication_num" = "1"') == len(GLUE_TABLES)
    assert "scope_glacier_demo" in ddl


def test_catalog_sql_is_placeholder_only():
    sql = (ROOT / "starrocks" / "init" / "01_iceberg_catalog.sql").read_text(encoding="utf-8")
    assert 'CREATE EXTERNAL CATALOG scope_glacier_iceberg' in sql
    assert '"iceberg.catalog.type" = "glue"' in sql
    assert '"${AWS_ACCESS_KEY_ID}"' in sql
    assert '"${AWS_SECRET_ACCESS_KEY}"' in sql
    assert "AKIA" not in sql
    rendered = sr.render_catalog_sql("TESTACCESSKEY", "test-secret", "us-east-1")
    assert "TESTACCESSKEY" in rendered
    assert "${AWS_ACCESS_KEY_ID}" not in rendered
    with pytest.raises(ValueError):
        sr.render_catalog_sql('bad"key', "secret", "us-east-1")


def test_bootstrap_does_not_trace_credentials():
    text = (ROOT / "starrocks" / "init" / "bootstrap.sh").read_text(encoding="utf-8")
    assert "set -x" not in text
    assert 'echo "$AWS_SECRET_ACCESS_KEY"' not in text
    assert "<<SQL" not in text
    assert "printf '%s\\n' \"$body\"" in text
    assert "scope_glacier_iceberg" in text
    subprocess.run(["bash", "-n", str(ROOT / "starrocks" / "init" / "bootstrap.sh")], check=True)
    subprocess.run(["bash", "-n", str(ROOT / "scripts" / "starrocks_demo.sh")], check=True)


def test_mcp_tool_matches_questions():
    tool = json.loads((ROOT / "starrocks" / "mcp" / "query_energy_lake.tool.json").read_text())
    assert tool["name"] == "query_energy_lake"
    assert tool["inputSchema"]["properties"]["question_id"]["enum"] == [q["id"] for q in sr.QUESTIONS]


def test_dry_run_prints_latency_table_and_agent_envelope():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "starrocks_query.py"), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "dry-run" in proc.stdout
    assert "price_dashboard" in proc.stdout
    assert "latency_ms" in proc.stdout
    assert "scope_glacier_demo" in proc.stdout

    agent = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "starrocks_agent_query.py"), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    envelope = json.loads(agent.stdout)
    assert envelope["jsonrpc"] == "2.0"
    assert envelope["result"]["isError"] is False
    payload = json.loads(envelope["result"]["content"][0]["text"])
    assert payload["tool"] == "query_energy_lake"
    assert payload["question_id"] == "wti_balance"
    assert payload["executed"] is False
    assert payload["latency_ms"] is None
    assert "LIMIT 12" in payload["sql"]


def test_readme_explains_the_spike():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## StarRocks spike" in readme
    assert "docker-compose.starrocks.yml" in readme
    assert "docs/STARROCKS.md" in readme
