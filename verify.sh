#!/usr/bin/env bash
# Ground-truth verification oracle for the tax_calc.py demo.
# Run with cwd = kilo-autonomy/ (the harness runs VERIFY_CMD with cwd=ROOT).
# Exits 0 only if every expected value matches the script's actual output.
set -u
cd "$(dirname "$0")/sandbox" || exit 2

fail=0
num() { grep -oE '\$[0-9,]+\.[0-9]{2}' | tr -d ',' | head -n1 | sed 's/^\$//'; }
check() {
  local name="$1" actual="$2" expected="$3"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name  (expected [$expected], got [$actual])"; fail=1
  else
    echo "PASS: $name"
  fi
}

# Case 1: single, gross 50000 -> income & total tax 4118.00
out=$(python3 tax_calc.py 50000 single)
check "single 50000 income tax"  "$(echo "$out" | grep 'Income tax' | num)"  "4118.00"
check "single 50000 total tax"   "$(echo "$out" | grep 'Total tax'  | num)"  "4118.00"

# Case 2: married_joint, gross 150000, gain 20000
out=$(python3 tax_calc.py 150000 married_joint --gain 20000)
check "married 150k+gain20k income tax"     "$(echo "$out" | grep 'Income tax' | num)"      "17521.00"
check "married 150k+gain20k cap gains tax"  "$(echo "$out" | grep 'Capital gains tax' | num)" "3000.00"
check "married 150k+gain20k total tax"      "$(echo "$out" | grep 'Total tax' | num)"       "20521.00"

# Case 3: gross 0 -> everything 0.00
out=$(python3 tax_calc.py 0 single)
check "gross 0 total tax" "$(echo "$out" | grep 'Total tax' | num)" "0.00"

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
