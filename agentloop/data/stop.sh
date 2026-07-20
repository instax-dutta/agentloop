#!/usr/bin/env bash
# Gracefully stop AgentLoop: set STOP, wait for a clean exit, then SIGTERM if needed.
set -u
cd "$(dirname "$0")"
touch STOP
if [ ! -f agentloop.pid ]; then
  echo "No running agent found."
  exit 0
fi
pid="$(cat agentloop.pid 2>/dev/null || true)"
if [ -z "${pid}" ] || ! kill -0 "$pid" 2>/dev/null; then
  rm -f agentloop.pid
  echo "No running agent found (stale pid file cleared)."
  exit 0
fi
echo "Stop signal set (STOP). Waiting for pid $pid to exit cleanly..."
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Agent halted."
    rm -f agentloop.pid
    exit 0
  fi
  sleep 0.5
done
# Still alive: ask it to stop (signal handler sets STOP again and finishes).
kill -TERM "$pid" 2>/dev/null || true
for _ in 1 2 3 4 5 6; do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Agent halted after SIGTERM."
    rm -f agentloop.pid
    exit 0
  fi
  sleep 0.5
done
echo "Agent still running after graceful wait; sending SIGKILL."
kill -KILL "$pid" 2>/dev/null || true
rm -f agentloop.pid
