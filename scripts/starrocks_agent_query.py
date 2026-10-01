#!/usr/bin/env python3
"""CLI stand-in for an MCP tools/call against StarRocks.

Prints a JSON-RPC result for one read-only energy question. The default
question, wti_balance, is the high-concurrency shape: WTI only, the last
90 days, and LIMIT 12. The tool schema is starrocks/mcp/query_energy_lake.tool.json.

    python scripts/starrocks_agent_query.py --dry-run
    python scripts/starrocks_agent_query.py wti_balance
    python scripts/starrocks_agent_query.py price_dashboard
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import starrocks_query as sr


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--agent" not in args:
        args = ["--agent", *args]
    return sr.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
