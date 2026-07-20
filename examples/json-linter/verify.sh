#!/usr/bin/env bash
# Verification oracle for the JSON linter example.
# Works from the project root (how AgentLoop invokes it) or standalone.
set -u

# Determine project root: script's directory -> up to examples/ -> up to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# When run from project root by AgentLoop, sandbox/ is at project root
SANDBOX="$PROJECT_ROOT/sandbox"

fail=0
check() {
  local name="$1" actual="$2" expected="$3"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name  (expected [$expected], got [$actual])"; fail=1
  else
    echo "PASS: $name"
  fi
}

# Create test files
echo '{"name": "test", "value": 42}' > /tmp/valid.json
echo '{"name": "test", "value": 42,}' > /tmp/invalid.json

# Check if the linter exists in the sandbox
if [ ! -f "$SANDBOX/json_linter.py" ]; then
  echo "FAIL: $SANDBOX/json_linter.py not found — has the agent created it?"
  exit 2
fi

# Valid JSON test
out=$(python3 "$SANDBOX/json_linter.py" /tmp/valid.json 2>&1 || true)
check "valid json exit" "$(echo "$out" | head -1)" "Valid JSON"

# Invalid JSON test
out=$(python3 "$SANDBOX/json_linter.py" /tmp/invalid.json 2>&1 || true)
check "invalid json error present" "$(echo "$out" | head -1 | grep -c 'line')" "1"

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
