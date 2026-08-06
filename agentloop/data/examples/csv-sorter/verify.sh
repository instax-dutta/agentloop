#!/usr/bin/env bash
# Verification oracle for the csv-sorter example.
# Held-out oracle with property-based testing: generates random record batches
# (with deliberate duplicate ids to check stability), records a reference
# sorter, and grades the agent's sorter on batches it has never seen.
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
SEAL="${ORACLE_SEAL:-csv-demo-secret}"

fail=0

if [ ! -f "$SANDBOX/csv_sorter.py" ]; then
  echo "FAIL: $SANDBOX/csv_sorter.py not found — has the agent created it?"
  exit 2
fi

# Reference sorter — stable sort by integer id.
cat > /tmp/ref_csv.py <<'PY'
import sys
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(0)
recs = [r for r in raw.split(";;") if r]
parsed = [(int(r.split(",", 1)[0]), r.split(",", 1)[1]) for r in recs]
parsed.sort(key=lambda t: t[0])  # Python sort is stable
print("\n".join(f"{i},{n}" for i, n in parsed))
PY

# Property-based input generation — 40 random batches, ~30% with duplicate ids.
python3 - <<'PY' > /tmp/cases.txt
import random
rng = random.Random(1337)
for _ in range(40):
    n = rng.randint(0, 8)
    ids = [rng.randint(0, 999) for _ in range(n)]
    if n and rng.random() < 0.3:            # force a duplicate id
        ids[rng.randrange(n)] = ids[rng.randrange(n)]
    names = ["alice", "bob", "carol", "zoe", "mike", "dana"]
    recs = [f"{i},{rng.choice(names)}" for i in ids]
    print(";;".join(recs))
PY

python3 -m agentloop.oracle record \
  --reference "python3 /tmp/ref_csv.py" \
  --inputs /tmp/cases.txt \
  --visible 3 \
  --out "$ORACLE_DIR/csv_oracle.json" \
  --seal "$SEAL" || { echo "FAIL: oracle record failed"; exit 2; }

python3 -m agentloop.oracle grade \
  --candidate "python3 $SANDBOX/csv_sorter.py" \
  --oracle "$ORACLE_DIR/csv_oracle.json" \
  --seal "$SEAL" || fail=1

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
