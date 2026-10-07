"""
Glacier Analysis Lambda Handler — computes composite energy signals and Bedrock AI analysis.

Orchestrated by Step Functions state machine:
1. Compute component scores (supply/demand, price momentum, geopolitical, seasonal)
2. Generate Glacier Signals
3. Call Bedrock for AI analysis via Converse API
4. Write signals to Iceberg
"""

import json
import logging
import os
from datetime import datetime

import boto3

from bedrock_client import resolve_bedrock_model_id
from cubiczan_resilience import resilient
from scope_core import (
    SafeAthenaClient,
    error_response,
    success_response,
    validate_in_allowlist,
)

logger = logging.getLogger(__name__)

SCORE_WEIGHTS = {"supply_demand": 0.30, "price_momentum": 0.25, "geopolitical": 0.25, "seasonal": 0.20}

# Allowlist of commodity codes that may be interpolated into Athena SQL.
# Any code outside this set is rejected before query construction to prevent
# SQL injection via a caller-controlled Step Functions event.
ALLOWED_COMMODITY_CODES = {"WTI", "BRENT", "HH", "RBOB", "HO"}

# Valid signal ratings allowed to be written to the Iceberg table.
ALLOWED_RATINGS = {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}


def _validate_commodity_code(code):
    """Return the code if it is in the allowlist, else raise.

    Thin wrapper over scope_core.validate_in_allowlist — the canonical
    SQL-injection guard shared across the scope-* repos.
    """
    return validate_in_allowlist(code, ALLOWED_COMMODITY_CODES, field="commodity_code")


def _validate_numeric(value, name, lo, hi):
    """Coerce value to float and ensure it falls within [lo, hi]."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} is not numeric: {value!r}")
    if num != num or num in (float("inf"), float("-inf")):
        raise ValueError(f"{name} is not finite: {value!r}")
    if not (lo <= num <= hi):
        raise ValueError(f"{name} out of range [{lo}, {hi}]: {num}")
    return num


@resilient(timeout=150, max_attempts=3)
def _run_athena_query(client, query, output_location):
    """Start an Athena query via SafeAthenaClient and block until it succeeds.

    The query start + terminal-state poll (including FAILED/CANCELLED detection
    and the timeout) come from scope_core.SafeAthenaClient. This wrapper keeps
    the @resilient decorator so transient StartQueryExecution / GetQueryExecution
    throttling is retried with exponential backoff + jitter and tripped by the
    circuit breaker after repeated failures.
    """
    query_execution_id = client.start(query, output_location=output_location)
    client.wait(query_execution_id)
    return query_execution_id


def _make_athena_client():
    """Build a SafeAthenaClient from the repo's Glue database / output config."""
    return SafeAthenaClient(
        boto3.client("athena"),
        database=os.environ.get("GLUE_DATABASE", "scope_glacier"),
        output_location=os.environ.get("ATHENA_OUTPUT", "s3://scope-glacier-queries/"),
    )


def compute_glacier_scores(event):
    """Compute composite Glacier scores for specified energy commodities.

    Expected event:
    {
        "commodity_codes": ["WTI", "BRENT", "HH"],
        "utilization_pct": 92.0,
        "inventory_days": 28.0
    }
    """
    commodity_codes = event.get("commodity_codes", ["WTI", "BRENT", "HH"])
    utilization_pct = _validate_numeric(event.get("utilization_pct", 92.0), "utilization_pct", 0.0, 100.0)
    inventory_days = _validate_numeric(event.get("inventory_days", 28.0), "inventory_days", 0.0, 365.0)

    client = _make_athena_client()
    s3_output = client.output_location

    signals = []
    for code in commodity_codes:
        try:
            # Reject any code not in the allowlist before it reaches the SQL string.
            code = _validate_commodity_code(code)
            query = f"""
            WITH latest_price AS (
                SELECT price_value, price_date FROM scope_glacier.price_series
                WHERE commodity_code = '{code}'
                ORDER BY price_date DESC LIMIT 1
            ),
            price_30d_ago AS (
                SELECT price_value FROM scope_glacier.price_series
                WHERE commodity_code = '{code}'
                  AND price_date >= DATE_ADD('DAY', -35, CURRENT_DATE)
                ORDER BY price_date ASC LIMIT 1
            ),
            vol AS (
                SELECT
                    STDDEV(price_value) AS daily_std
                FROM scope_glacier.price_series
                WHERE commodity_code = '{code}'
                  AND price_date >= DATE_ADD('DAY', -25, CURRENT_DATE)
            )
            SELECT
                '{code}' AS commodity_code,
                (SELECT price_value FROM latest_price) AS latest_price,
                CASE
                    WHEN (SELECT price_value FROM latest_price) > 0
                        AND (SELECT price_value FROM price_30d_ago) > 0
                    THEN ROUND(
                        ((SELECT price_value FROM latest_price) - (SELECT price_value FROM price_30d_ago))
                        / (SELECT price_value FROM price_30d_ago) * 100, 2)
                    ELSE 0
                END AS return_30d_pct,
                ROUND(COALESCE((SELECT daily_std FROM vol), 0) * (252.0 ** 0.5) * 100, 2) AS annualized_volatility_pct
            """

            query_execution_id = _run_athena_query(
                client, query, f"{s3_output}glacier/scores/"
            )

            # Compute component scores
            sd_score = 50.0
            if utilization_pct > 95:
                sd_score += 30
            elif utilization_pct > 90:
                sd_score += 20
            elif utilization_pct < 75:
                sd_score -= 15
            if inventory_days < 25:
                sd_score += 20
            elif inventory_days > 60:
                sd_score -= 10

            glacier_score = round(
                sd_score * SCORE_WEIGHTS["supply_demand"]
                + 50.0 * SCORE_WEIGHTS["price_momentum"]
                + 50.0 * SCORE_WEIGHTS["geopolitical"]
                + 50.0 * SCORE_WEIGHTS["seasonal"],
                2,
            )

            rating = "Hold"
            if glacier_score >= 80:
                rating = "Strong Buy"
            elif glacier_score >= 65:
                rating = "Buy"
            elif glacier_score >= 35:
                rating = "Hold"
            elif glacier_score >= 20:
                rating = "Sell"
            else:
                rating = "Strong Sell"

            signals.append({
                "commodity_code": code,
                "query_id": query_execution_id,
                "glacier_score": glacier_score,
                "signal_rating": rating,
                "supply_demand_score": sd_score,
                "status": "submitted",
            })
            logger.info(f"Computed Glacier score for {code}: {glacier_score} ({rating})")

        except Exception as e:
            logger.error(f"Error computing score for {code}: {e}")
            signals.append({"commodity_code": code, "status": "error", "error": str(e)})

    return signals


def invoke_bedrock_analysis(commodity_code: str, signal_data: dict) -> str:
    """Invoke Bedrock Converse API for energy market AI analysis.

    The model id is resolved before any retry or API call. An Anthropic override
    raises immediately. Transient Bedrock throttling is retried inside
    ``_invoke_bedrock_converse``.
    """
    model_id = resolve_bedrock_model_id()
    return _invoke_bedrock_converse(commodity_code, signal_data, model_id)


@resilient(timeout=60, max_attempts=3)
def _invoke_bedrock_converse(commodity_code: str, signal_data: dict, model_id: str) -> str:
    """Call Converse and degrade to an "Analysis unavailable" string after retries.

    Transient throttling and timeouts are retried with exponential backoff and
    jitter. The model id is already validated by the caller.
    """
    bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    prompt = f"""Analyze {commodity_code} energy market:

Glacier Score: {signal_data.get('glacier_score', 'N/A')}/100 ({signal_data.get('signal_rating', 'Hold')})
- Supply/Demand Score: {signal_data.get('supply_demand_score', 50):.0f}/100
- Price Momentum Score: {signal_data.get('price_momentum_score', 50):.0f}/100
- Geopolitical Score: {signal_data.get('geopolitical_score', 50):.0f}/100
- Seasonal Score: {signal_data.get('seasonal_score', 50):.0f}/100
- Latest Price: {signal_data.get('latest_price', 'N/A')}
- 30-Day Return: {signal_data.get('return_30d_pct', 'N/A')}%
- Annualized Volatility: {signal_data.get('annualized_volatility', 'N/A')}%

Provide 2-3 paragraphs covering supply/demand outlook, geopolitical risks, seasonal factors, and price direction."""

    try:
        response = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            system=[{"text": "You are a senior energy market analyst. Be data-driven and concise."}],
            inferenceConfig={"maxTokens": 800, "temperature": 0.3},
        )
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        return "".join(cb.get("text", "") for cb in content_blocks)
    except Exception as e:
        logger.error(f"Bedrock analysis failed for {commodity_code}: {e}")
        return f"Analysis unavailable: {str(e)}"


def write_signals_to_iceberg(signals: list):
    """Write Glacier signals to Iceberg table via Athena."""
    client = _make_athena_client()
    database = client.database
    s3_output = client.output_location

    for signal in signals:
        if signal.get("status") != "analyzed":
            continue
        try:
            # Validate every value that gets interpolated into the SQL string.
            code = _validate_commodity_code(signal["commodity_code"])
            rating = signal.get("signal_rating", "Hold")
            if rating not in ALLOWED_RATINGS:
                raise ValueError(f"Disallowed signal_rating: {rating!r}")
            sd_score = _validate_numeric(signal.get("supply_demand_score", 50), "supply_demand_score", -1000, 1000)
            pm_score = _validate_numeric(signal.get("price_momentum_score", 50), "price_momentum_score", -1000, 1000)
            geo_score = _validate_numeric(signal.get("geopolitical_score", 50), "geopolitical_score", -1000, 1000)
            seas_score = _validate_numeric(signal.get("seasonal_score", 50), "seasonal_score", -1000, 1000)
            g_score = _validate_numeric(signal.get("glacier_score", 50), "glacier_score", -1000, 1000)
            conf_score = _validate_numeric(signal.get("confidence_score", 0.5), "confidence_score", 0.0, 1.0)

            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            # signal_id is derived from the allowlisted code, so it is safe.
            signal_id = f"{code}_{ts}"
            # Free-text fields are escaped for single quotes; their values are not
            # caller-trusted identifiers so escaping (not allowlisting) is appropriate.
            analysis = signal.get("ai_analysis", "")[:4000].replace("'", "''")
            data_sources = json.dumps(signal.get("data_sources", [])).replace("'", "''")

            query = f"""
            INSERT INTO {database}.glacier_signals
            VALUES (
                '{signal_id}',
                '{code}',
                TIMESTAMP '{datetime.utcnow().isoformat()}',
                {sd_score},
                {pm_score},
                {geo_score},
                {seas_score},
                {g_score},
                '{rating}',
                '{analysis}',
                {conf_score},
                '{data_sources}'
            )
            """
            _run_athena_query(
                client, query, f"{s3_output}signals/write/"
            )
        except Exception as e:
            logger.error(f"Error writing signal for {signal.get('commodity_code', '?')}: {e}")


def handler(event, context):
    """AWS Lambda entry point for Glacier analysis pipeline.

    Step Functions passes:
    {
        "step": "compute_scores" | "bedrock_analysis" | "write_signals",
        "commodity_codes": ["WTI", "BRENT", "HH"],
        "signals": [...]  // for bedrock_analysis or write_signals steps
    }
    """
    logger.info(f"Glacier analysis Lambda triggered: {json.dumps(event)[:500]}")

    step = event.get("step", "compute_scores")

    if step == "compute_scores":
        signals = compute_glacier_scores(event)
        return success_response({"step": step, "signals": signals})

    elif step == "bedrock_analysis":
        signals = event.get("signals", [])
        for signal in signals:
            code = signal.get("commodity_code", "")
            analysis = invoke_bedrock_analysis(code, signal)
            signal["ai_analysis"] = analysis
            signal["status"] = "analyzed"
        return success_response({"step": step, "signals": signals})

    elif step == "write_signals":
        write_signals_to_iceberg(event.get("signals", []))
        return success_response({"step": step, "status": "completed"})

    return error_response(f"Unknown step: {step}", status_code=400)
