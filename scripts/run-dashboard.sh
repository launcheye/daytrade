#!/usr/bin/env bash
#
# Launch the daytrade dashboard for private remote access over Tailscale.
#
# Binds 0.0.0.0 so another device on your Tailscale network (e.g. your phone)
# can reach it, and requires a password. Tailscale is a private mesh network —
# the dashboard is NOT exposed to the public internet.
#
# Paper / simulation only. The dashboard is read-only: no real trading,
# no wallets, no orders, no money movement.
#
# Usage:
#   ./scripts/run-dashboard.sh                 # prompts for a password
#   DASHBOARD_PASSWORD=secret ./scripts/run-dashboard.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${DASHBOARD_PASSWORD:-}" ]; then
  read -rsp "Set a dashboard password: " DASHBOARD_PASSWORD
  echo
fi
if [ -z "${DASHBOARD_PASSWORD}" ]; then
  echo "error: empty password — refusing to start an unprotected dashboard" >&2
  exit 1
fi
export DASHBOARD_PASSWORD

HOST="${DASHBOARD_HOST:-0.0.0.0}"
PORT="${DASHBOARD_PORT:-8000}"

echo "Dashboard starting on ${HOST}:${PORT} (password protected)."
if command -v tailscale >/dev/null 2>&1; then
  TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  [ -n "${TS_IP}" ] && echo "Reach it from your phone at: http://${TS_IP}:${PORT}"
fi

PYTHONPATH=src exec python3 -m daytrade dashboard --host "${HOST}" --port "${PORT}"
