#!/usr/bin/env bash
# Verification oracle for the python-type-checker example.
# Exit-code oracle: py_compile always; mypy when available. Both must exit 0.
# Also spot-checks behaviour of the annotated function.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/sandbox" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
SANDBOX="${AGENTLOOP_SANDBOX:-$PROJECT_ROOT/sandbox}"
fail=0

MOD="$SANDBOX/typed_module.py"
if [ ! -f "$MOD" ]; then
  echo "FAIL: $MOD not found — has the agent created it?"
  exit 2
fi

echo "== py_compile =="
if python3 -m py_compile "$MOD"; then
  echo "PASS: compiles"
else
  echo "FAIL: py_compile exited non-zero"
  fail=1
fi

if command -v mypy >/dev/null 2>&1; then
  echo "== mypy =="
  if (cd "$SANDBOX" && mypy typed_module.py); then
    echo "PASS: mypy clean"
  else
    echo "FAIL: mypy found type errors (all params/returns must be annotated)"
    fail=1
  fi
else
  echo "NOTE: mypy not installed — falling back to annotation grep"
  if grep -q "list\[int\]" "$MOD" && grep -q "dict\[str, int\]" "$MOD"; then
    echo "PASS: required annotations present"
  else
    echo "FAIL: expected annotations list[int] and dict[str, int] not found"
    fail=1
  fi
fi

echo "== behaviour =="
OUT=$(cd "$SANDBOX" && python3 -c "
import typed_module
print(typed_module.classify([1, -2, 0, 3, -4, 0]))
")
EXPECTED="{'positive': 2, 'negative': 2, 'zero': 2}"
if [ "$OUT" = "$EXPECTED" ]; then
  echo "PASS: classify() behaves correctly"
else
  echo "FAIL: classify() -> $OUT (expected $EXPECTED)"
  fail=1
fi

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
