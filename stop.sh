#!/usr/bin/env bash
# Gracefully stop the autopilot: creates STOP, then kills the process.
set -u
cd "$(dirname "$0")"
touch STOP
if [ -f agentloop.pid ] && kill -0 "$(cat agentloop.pid)" 2>/dev/null; then
  kill "$(cat agentloop.pid)" 2>/dev/null
  echo "Stop signal sent. Agent will halt at the next step."
else
  echo "No running agent found."
fi
