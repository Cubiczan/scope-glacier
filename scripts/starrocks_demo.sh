#!/usr/bin/env bash
# Start the local FE/BE, wait until bootstrap finishes, print query latency.

set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
compose=(docker compose -f docker-compose.starrocks.yml)

"${compose[@]}" up -d

echo "Waiting for starrocks-init to finish"
ready=0
for _ in $(seq 1 90); do
  cid=$("${compose[@]}" ps -aq starrocks-init || true)
  if [[ -n "${cid}" ]]; then
    status=$(docker inspect -f '{{.State.Status}}' "$cid")
    if [[ "$status" == "exited" ]]; then
      code=$(docker inspect -f '{{.State.ExitCode}}' "$cid")
      if [[ "$code" != "0" ]]; then
        "${compose[@]}" logs starrocks-init
        echo "starrocks-init exited ${code}" >&2
        exit 1
      fi
      ready=1
      break
    fi
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  "${compose[@]}" logs starrocks-init
  echo "timed out waiting for bootstrap complete" >&2
  exit 1
fi

python3 -c "import pymysql" 2>/dev/null || python3 -m pip install pymysql
python3 scripts/starrocks_query.py --source fixture
python3 scripts/starrocks_agent_query.py --source fixture wti_balance
