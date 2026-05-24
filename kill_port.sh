#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8088}"

collect_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null | sort -u
    return 0
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null \
      | awk -v port="${PORT}" '$4 ~ ":" port "$" { print $NF }' \
      | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
      | sort -u
    return 0
  fi

  return 1
}

PIDS="$(collect_pids || true)"

if [[ -z "${PIDS}" ]]; then
  echo "No process is listening on port ${PORT}."
  exit 0
fi

echo "Stopping process(es) on port ${PORT}: ${PIDS}"
kill -TERM ${PIDS} 2>/dev/null || true
sleep 1

REMAINING="$(collect_pids || true)"
if [[ -n "${REMAINING}" ]]; then
  echo "Force killing remaining process(es): ${REMAINING}"
  kill -KILL ${REMAINING} 2>/dev/null || true
  sleep 0.5
fi

FINAL="$(collect_pids || true)"
if [[ -n "${FINAL}" ]]; then
  echo "Some process(es) still appear to be bound to port ${PORT}: ${FINAL}"
  exit 1
fi

echo "Port ${PORT} is now free."
