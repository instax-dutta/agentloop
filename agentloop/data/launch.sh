#!/usr/bin/env bash
# Turnkey launcher for AgentLoop — the autonomy wrapper for your coding agent.
# Usage: ./launch.sh   (runs in background, safe, idempotent)
set -u
cd "$(dirname "$0")"
ROOT="$(pwd)"

# 1) in CLI mode (default) there is no key to supply — you bring your own harness.
#    Only direct mode needs KILO_API_KEY.
MODE="${AGENT_MODE:-cli}"
if [ "$MODE" = "direct" ] && [ ! -f .env ] && [ -z "${KILO_API_KEY:-}" ] && [ -z "${KILOCODE_API_KEY:-}" ]; then
  echo "==================================================================="
  echo " direct mode needs a key. Either set AGENT_MODE=cli (default, bring"
  echo " your own agent CLI like opencode/kilocode/claude), or put"
  echo " KILO_API_KEY=sk-... in $ROOT/.env for direct mode."
  echo "==================================================================="
  exit 1
fi

# 2) don't start a second copy
if [ -f agentloop.pid ] && kill -0 "$(cat agentloop.pid)" 2>/dev/null; then
  echo "Already running (pid $(cat agentloop.pid)). Tail: tail -f $ROOT/agentloop.log"
  exit 0
fi

# 3) ensure sandbox exists and is a git repo (for checkpoints)
mkdir -p sandbox
if [ ! -d sandbox/.git ]; then
  git -C sandbox init -q
  git -C sandbox config user.email "agentloop@local"
  git -C sandbox config user.name "agentloop"
fi

# 4) clear any stale STOP signal and launch
rm -f STOP
nohup python3 -m agentloop >> agentloop.log 2>&1 &
echo "Launched pid $!. Mode=$MODE. Logs: tail -f $ROOT/agentloop.log  | Stop: ./stop.sh"
