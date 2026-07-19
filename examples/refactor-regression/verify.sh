#!/usr/bin/env bash
# Verification oracle for the refactor-regression example.
# Uses held-out oracle to ensure refactored code matches original on unseen inputs.
set -u
cd "$(dirname "$0")" || exit 2

fail=0

# 1. Create the reference (original) code and candidate (refactored) code
mkdir -p .agentloop/oracle_sealed

# Reference: original implementation
cat > /tmp/ref.py << 'PY'
import json, sys
def process(data):
    result = []
    for i in range(len(data)):
        d = data[i]
        x = d['x']
        y = d['y']
        if x > 0:
            if y > 0:
                result.append({'label': 'A', 'val': x + y})
            else:
                result.append({'label': 'B', 'val': x - y})
        else:
            if y > 0:
                result.append({'label': 'C', 'val': y - x})
            else:
                result.append({'label': 'D', 'val': x * y})
    return result
if __name__ == '__main__':
    inp = json.loads(sys.stdin.read())
    out = process(inp)
    print(json.dumps(out))
PY

# Generate 200 random test cases
python3 -c "
import random, json
random.seed(42)
cases = []
for _ in range(200):
    n = random.randint(1, 5)
    data = [{'x': random.randint(-10, 10), 'y': random.randint(-10, 10)} for _ in range(n)]
    cases.append(json.dumps(data))
with open('/tmp/cases.txt', 'w') as f:
    for c in cases:
        f.write(c + '\n')
print(f'generated {len(cases)} cases')
" || exit 2

# Record the reference behaviour
python3 oracle.py record \
  --reference "python3 /tmp/ref.py" \
  --inputs /tmp/cases.txt \
  --visible 10 \
  --out .agentloop/oracle_sealed/refactor_oracle.json \
  --seal "${ORACLE_SEAL:-refactor-demo-secret}" || exit 2

# Grade the candidate (the refactored code in the sandbox)
python3 oracle.py grade \
  --candidate "python3 sandbox/refactor_target.py" \
  --oracle .agentloop/oracle_sealed/refactor_oracle.json \
  --seal "${ORACLE_SEAL:-refactor-demo-secret}" || fail=1

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
