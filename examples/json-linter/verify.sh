#!/usr/bin/env bash
# Verification oracle for the JSON linter example.
set -u
cd "$(dirname "$0")/sandbox" || exit 2

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

# Valid JSON test
out=$(python3 sandbox/json_linter.py /tmp/valid.json 2>&1 || true)
check "valid json exit" "$(echo "$out" | head -1)" "Valid JSON"

# Invalid JSON test
out=$(python3 sandbox/json_linter.py /tmp/invalid.json 2>&1 || true)
check "invalid json error present" "$(echo "$out" | head -1 | grep -c 'line')" "1"

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
