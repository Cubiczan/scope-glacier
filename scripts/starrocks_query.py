#!/usr/bin/env python3
"""Run Scope.Glacier analytical questions on StarRocks and print latency.

The SQL files in starrocks/sql/ answer the same questions as the Athena views
in src/aws/athena_views/. --source iceberg reads the Glue Iceberg catalog.
--source fixture reads the native demo tables. auto prefers Iceberg when the
catalog responds.

    python scripts/starrocks_query.py
    python scripts/starrocks_query.py --dry-run
    python scripts/starrocks_query.py --register-iceberg --source iceberg
    python scripts/starrocks_query.py --agent wti_balance
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "starrocks" / "sql"
CATALOG_SQL = ROOT / "starrocks" / "init" / "01_iceberg_catalog.sql"

FIXTURE_DB = "scope_glacier_demo"
ICEBERG_CATALOG = "scope_glacier_iceberg"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+\d+", re.IGNORECASE)
COMMENT_RE = re.compile(r"--[^\n]*")

QUESTIONS = (
    {
        "id": "price_dashboard",
        "title": "30-day price level, volatility, and returns",
        "athena_view": "scope_glacier.energy_price_dashboard_v",
        "file": "price_dashboard.sql",
        "order_by": "latest_price DESC",
        "view": "energy_price_dashboard_v",
    },
    {
        "id": "supply_demand",
        "title": "Implied balance, inventory cover, and 4-week gap",
        "athena_view": "scope_glacier.supply_demand_fundamentals_v",
        "file": "supply_demand.sql",
        "order_by": "commodity_code, `date` DESC",
        "view": "supply_demand_fundamentals_v",
    },
    {
        "id": "infrastructure_disruption",
        "title": "Pipeline and refinery disruption and offline capacity",
        "athena_view": "scope_glacier.infrastructure_disruption_v",
        "file": "infrastructure_disruption.sql",
        "order_by": "is_disrupted DESC, estimated_offline_bpd DESC",
        "view": "infrastructure_disruption_v",
    },
    {
        "id": "latest_signal",
        "title": "Latest Glacier composite signal per commodity",
        "athena_view": "scope_glacier.glacier_signals",
        "file": "latest_signal.sql",
        "order_by": "glacier_score DESC",
        "view": None,
    },
    {
        "id": "wti_balance",
        "title": "WTI implied balance, last 90 days (agent query)",
        "athena_view": "scope_glacier.supply_demand_fundamentals_v",
        "file": "wti_balance.sql",
        "order_by": None,
        "view": None,
    },
)

TOOL_NAME = "query_energy_lake"


def load_dotenv() -> None:
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        return
    _load()


def question_by_id(question_id: str) -> dict:
    for question in QUESTIONS:
        if question["id"] == question_id:
            return question
    known = ", ".join(q["id"] for q in QUESTIONS)
    raise SystemExit(f"Unknown question {question_id!r}. Choose from: {known}")


def load_sql(question: dict) -> str:
    path = SQL_DIR / question["file"]
    return path.read_text(encoding="utf-8").strip().rstrip(";")


def qualify(source: str, glue_database: str) -> str:
    if source == "fixture":
        return FIXTURE_DB
    if source == "iceberg":
        if not IDENTIFIER.match(glue_database):
            raise SystemExit(f"GLUE_DATABASE must be a bare identifier, got {glue_database!r}")
        return f"{ICEBERG_CATALOG}.{glue_database}"
    raise SystemExit(f"Unknown source {source!r}")


def render_sql(question: dict, database: str, limit: int) -> str:
    template = load_sql(question)
    if "{db}" not in template:
        raise SystemExit(f"{question['file']} is missing the {{db}} placeholder")
    sql = template.format(db=database).strip()
    code = COMMENT_RE.sub("", sql)
    order_by = question.get("order_by")
    if order_by and not ORDER_BY_RE.search(code):
        sql = f"{sql}\nORDER BY {order_by}"
    if limit > 0 and not LIMIT_RE.search(code):
        sql = f"{sql}\nLIMIT {int(limit)}"
    return sql


def render_catalog_sql(access_key: str, secret_key: str, region: str) -> str:
    for label, value in (
        ("AWS_ACCESS_KEY_ID", access_key),
        ("AWS_SECRET_ACCESS_KEY", secret_key),
        ("AWS_REGION", region),
    ):
        if not value:
            raise ValueError(f"{label} is empty")
        if any(ch in value for ch in "\"\\\n\r;"):
            raise ValueError(f"{label} contains characters this demo will not embed in SQL")
    if not re.fullmatch(r"[a-z0-9-]+", region):
        raise ValueError(f"AWS_REGION must look like a region name, got {region!r}")
    sql = CATALOG_SQL.read_text(encoding="utf-8")
    sql = sql.replace("${AWS_ACCESS_KEY_ID}", access_key)
    sql = sql.replace("${AWS_SECRET_ACCESS_KEY}", secret_key)
    sql = sql.replace("${AWS_REGION}", region)
    if "${" in sql:
        raise ValueError("Iceberg catalog SQL still contains a placeholder")
    return sql


def _cell(value: object, width: int = 36) -> str:
    if value is None:
        text = ""
    elif isinstance(value, float):
        text = f"{value:.4g}"
    else:
        text = str(value)
    text = text.replace("\n", " ")
    if len(text) > width:
        return text[: width - 1] + "…"
    return text


def format_rows(rows: list[dict], max_rows: int = 8) -> str:
    if not rows:
        return "(no rows)"
    preview = rows[:max_rows]
    columns = list(preview[0].keys())
    header = " | ".join(columns)
    lines = [header, " | ".join("---" for _ in columns)]
    for row in preview:
        lines.append(" | ".join(_cell(row.get(col)) for col in columns))
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} more rows")
    return "\n".join(lines)


def query_payload(question, source, database, sql, rows, latency_ms, executed: bool) -> dict:
    return {
        "tool": TOOL_NAME,
        "question_id": question["id"],
        "title": question["title"],
        "athena_view": question["athena_view"],
        "source": source,
        "database": database,
        "executed": executed,
        "sql": sql,
        "latency_ms": None if latency_ms is None else round(latency_ms, 2),
        "row_count": len(rows),
        "rows": rows,
    }


def mcp_tools_call_result(payload: dict, *, is_error: bool = False) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "scope-glacier-starrocks",
        "result": {
            "content": [
                {"type": "text", "text": json.dumps(payload, default=str, indent=2)}
            ],
            "isError": is_error,
        },
    }


def connect(host: str, port: int, user: str, password: str):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError:
        raise SystemExit("pymysql is required: pip install pymysql")
    try:
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            cursorclass=DictCursor,
            connect_timeout=5,
            read_timeout=120,
            autocommit=True,
        )
    except Exception as exc:
        raise SystemExit(
            f"Could not connect to StarRocks at {host}:{port} ({exc}).\n"
            "Start the demo with: docker compose -f docker-compose.starrocks.yml up -d"
        )


def _names(rows: list[dict]) -> list[str]:
    found = []
    for row in rows:
        if not row:
            continue
        for key in ("Catalog", "catalog", "Database", "database"):
            if key in row and row[key] is not None:
                found.append(str(row[key]))
                break
        else:
            found.append(str(next(iter(row.values()))))
    return found


def resolve_source(conn, requested: str, glue_database: str) -> tuple[str, str]:
    if requested in ("fixture", "iceberg"):
        return requested, qualify(requested, glue_database)
    with conn.cursor() as cur:
        try:
            cur.execute("SHOW CATALOGS")
            catalogs = _names(list(cur.fetchall()))
        except Exception:
            catalogs = []
        if ICEBERG_CATALOG in catalogs:
            try:
                cur.execute(f"SHOW DATABASES FROM {ICEBERG_CATALOG}")
                databases = _names(list(cur.fetchall()))
                if glue_database in databases:
                    return "iceberg", qualify("iceberg", glue_database)
            except Exception:
                pass
    return "fixture", qualify("fixture", glue_database)


def register_iceberg(conn) -> None:
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    region = os.environ.get("AWS_REGION", "us-east-1")
    try:
        sql = render_catalog_sql(access_key, secret_key, region)
    except ValueError as exc:
        raise SystemExit(str(exc))
    with conn.cursor() as cur:
        cur.execute("SHOW CATALOGS")
        if ICEBERG_CATALOG in _names(list(cur.fetchall())):
            print(f"Iceberg catalog {ICEBERG_CATALOG} already registered")
            return
        try:
            cur.execute(sql)
        except Exception as exc:
            raise SystemExit(f"Iceberg catalog registration failed ({exc.__class__.__name__})")
    print(f"Iceberg catalog {ICEBERG_CATALOG} registered")


def execute_question(conn, sql: str) -> tuple[list[dict], float]:
    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = list(cur.fetchall())
    elapsed_ms = (time.perf_counter() - started) * 1000
    return rows, elapsed_ms


def print_summary(results: list[dict]) -> None:
    print(f"{'question':<28} {'rows':>6} {'latency_ms':>12}")
    for item in results:
        latency = item["latency_ms"]
        latency_text = "-" if latency is None else f"{latency:.2f}"
        print(f"{item['question_id']:<28} {item['row_count']:>6} {latency_text:>12}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question_id", nargs="?", default=None)
    parser.add_argument("--agent", action="store_true", help="print an MCP tools/call result")
    parser.add_argument("--dry-run", action="store_true", help="render SQL and skip the connection")
    parser.add_argument("--list", action="store_true", help="list question ids")
    parser.add_argument("--register-iceberg", action="store_true")
    parser.add_argument(
        "--source",
        choices=("auto", "iceberg", "fixture"),
        default=os.environ.get("STARROCKS_SOURCE", "auto"),
    )
    parser.add_argument("--limit", type=int, default=500, help="row cap; 0 disables it")
    parser.add_argument("--host", default=os.environ.get("STARROCKS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("STARROCKS_PORT", "9030")))
    parser.add_argument("--user", default=os.environ.get("STARROCKS_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("STARROCKS_PASSWORD", ""))
    parser.add_argument(
        "--glue-database",
        default=os.environ.get("GLUE_DATABASE", "scope_glacier"),
    )
    return parser.parse_args(argv)


def selected_questions(args: argparse.Namespace) -> list[dict]:
    if args.question_id:
        return [question_by_id(args.question_id)]
    if args.agent:
        return [question_by_id("wti_balance")]
    return list(QUESTIONS)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list:
        for question in QUESTIONS:
            print(f"{question['id']:<28} {question['title']}")
        return 0
    if args.limit < 0:
        raise SystemExit("--limit must be >= 0")

    questions = selected_questions(args)
    if args.dry_run:
        source = "fixture" if args.source == "auto" else args.source
        database = qualify(source, args.glue_database)
        payloads = []
        for question in questions:
            sql = render_sql(question, database, args.limit)
            payloads.append(query_payload(question, source, database, sql, [], None, False))
        if args.agent:
            body = payloads[0] if len(payloads) == 1 else payloads
            print(json.dumps(mcp_tools_call_result(body), indent=2))
        else:
            print(f"dry-run source={source} database={database}")
            print_summary(payloads)
            for payload in payloads:
                print(f"\n-- {payload['question_id']} (Athena: {payload['athena_view']})")
                print(payload["sql"])
        return 0

    conn = connect(args.host, args.port, args.user, args.password)
    try:
        if args.register_iceberg:
            register_iceberg(conn)
        source, database = resolve_source(conn, args.source, args.glue_database)
        payloads = []
        for question in questions:
            sql = render_sql(question, database, args.limit)
            try:
                rows, latency_ms = execute_question(conn, sql)
            except Exception as exc:
                payload = query_payload(question, source, database, sql, [], None, False)
                payload["error"] = exc.__class__.__name__
                if args.agent:
                    print(json.dumps(mcp_tools_call_result(payload, is_error=True), indent=2))
                else:
                    print(f"{question['id']} failed ({exc.__class__.__name__})", file=sys.stderr)
                return 1
            payloads.append(query_payload(question, source, database, sql, rows, latency_ms, True))
    finally:
        conn.close()

    if args.agent:
        body = payloads[0] if len(payloads) == 1 else payloads
        print(json.dumps(mcp_tools_call_result(body), default=str, indent=2))
        return 0

    print(f"source={source} database={database}")
    print("Athena answers these questions from the Glue views; this run used StarRocks.")
    print_summary(payloads)
    for payload in payloads:
        print(f"\n-- {payload['question_id']}  {payload['latency_ms']:.2f} ms")
        print(format_rows(payload["rows"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
