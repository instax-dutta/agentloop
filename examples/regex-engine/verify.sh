#!/usr/bin/env bash
# Verification oracle for the regex-engine example.
# Held-out oracle with adversarial inputs: records a reference regex matcher's
# behaviour on generated cases, then grades the agent's matcher on cases it has
# never seen (the first 3 are visible, the rest are held-out and sealed).
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/sandbox" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
SANDBOX="${AGENTLOOP_SANDBOX:-$PROJECT_ROOT/sandbox}"
ORACLE_DIR="$SCRIPT_DIR/.agentloop/oracle_sealed"
mkdir -p "$ORACLE_DIR"
SEAL="${ORACLE_SEAL:-regex-demo-secret}"

fail=0

if [ ! -f "$SANDBOX/regex_matcher.py" ]; then
  echo "FAIL: $SANDBOX/regex_matcher.py not found — has the agent created it?"
  exit 2
fi

# Reference matcher — Python's re, exactly the semantics the goal demands.
cat > /tmp/ref_regex.py <<'PY'
import re, sys
lines = sys.stdin.read().splitlines()
pattern = lines[0] if lines else ""
text = lines[1] if len(lines) > 1 else ""
try:
    print("MATCH" if re.search(pattern, text) else "NO_MATCH")
except re.error:
    print("ERROR")
PY

# Adversarial cases: valid + invalid patterns, empties, escapes, anchors.
cat > /tmp/cases.txt <<'EOF'
(a|b)+c
ababc
^[0-9]{3}-[0-9]{4}$
123-4567
\bcat\b
a cat and a dog
^$
foo\.bar
foo.bar
\d{2,4}
12345
a*
bbb
[abc]+
xxcbx
(
unclosed
[z-a]
weird range
(?:nested){2,3}
nestnestnest
\s+
  spaced
^\s*$
	 tab
.*
anything
EOF

python3 -m agentloop.oracle record \
  --reference "python3 /tmp/ref_regex.py" \
  --inputs /tmp/cases.txt \
  --visible 3 \
  --out "$ORACLE_DIR/regex_oracle.json" \
  --seal "$SEAL" || { echo "FAIL: oracle record failed"; exit 2; }

python3 -m agentloop.oracle grade \
  --candidate "python3 $SANDBOX/regex_matcher.py" \
  --oracle "$ORACLE_DIR/regex_oracle.json" \
  --seal "$SEAL" || fail=1

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
