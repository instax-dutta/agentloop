#!/usr/bin/env bash
# Verification oracle for the roman-numeral-converter community verifier.
#
# Pattern: held-out oracle (tag: held-out-oracle). Records a trusted reference
# implementation on generated inputs (only 3 visible), seals the held-out
# cases, and grades the agent's roman.py on EVERY input — it only passes if it
# is correct on cases it never saw. This is the anti-overfitting moat: the
# agent cannot pass by memorizing the visible examples.
#
# Requires agentloop-cli (the `agentloop.oracle` module) to be installed.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Locate the project root: the nearest ancestor containing a sandbox/ dir.
resolve_root() {
  local dir="$SCRIPT_DIR"
  while [ "$dir" != "/" ]; do
    if [ -d "$dir/sandbox" ]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

if [ -n "${AGENTLOOP_SANDBOX:-}" ]; then
  SANDBOX="$AGENTLOOP_SANDBOX"
elif PROJECT_ROOT="$(resolve_root || true)" && [ -n "$PROJECT_ROOT" ]; then
  SANDBOX="$PROJECT_ROOT/sandbox"
else
  echo "FAIL: could not locate a sandbox/ directory."
  echo "      Fix: place verify.sh (or its folder) next to your sandbox/, or set"
  echo "      AGENTLOOP_SANDBOX=/abs/path/to/sandbox"
  exit 2
fi

if [ ! -f "$SANDBOX/roman.py" ]; then
  echo "FAIL: $SANDBOX/roman.py not found — has the agent created it?"
  exit 2
fi

# --- Reference implementation (this DEFINES the exact spec) -----------------
cat > /tmp/ref_roman.py <<'PY'
import sys

VALUES = [("M", 1000), ("CM", 900), ("D", 500), ("CD", 400), ("C", 100),
          ("XC", 90), ("L", 50), ("XL", 40), ("X", 10), ("IX", 9),
          ("V", 5), ("IV", 4), ("I", 1)]


def to_roman(n):
    out = []
    for sym, val in VALUES:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def from_roman(s):
    total = 0
    i = 0
    while i < len(s):
        for sym, val in VALUES:
            if s.startswith(sym, i):
                total += val
                i += len(sym)
                break
        else:
            return None
    return total


def main():
    line = sys.stdin.read().strip()
    if not line:
        return
    if line.isdigit():
        n = int(line)
        print(to_roman(n) if 1 <= n <= 3999 else "INVALID")
    else:
        r = from_roman(line)
        print(r if r is not None else "INVALID")


if __name__ == "__main__":
    main()
PY

# --- Deterministic inputs: 3 visible + ~78 held-out --------------------------
python3 - <<'PY' > /tmp/roman_cases.txt
import random

VALUES = [("M", 1000), ("CM", 900), ("D", 500), ("CD", 400), ("C", 100),
          ("XC", 90), ("L", 50), ("XL", 40), ("X", 10), ("IX", 9),
          ("V", 5), ("IV", 4), ("I", 1)]


def to_roman(n):
    out = []
    for sym, val in VALUES:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


rng = random.Random(1337)
cases = ["1", "I", "5"]              # the 3 VISIBLE cases
for _ in range(36):                  # 72 generated held-out cases
    n = rng.randint(1, 3999)
    cases.append(str(n))
    cases.append(to_roman(n))
cases += ["3999", "MCMXCIV", "0", "ABC", "444", "CDXLIV"]  # edge + invalid
print("\n".join(cases))
PY

# --- Record the reference (sealed; held-out cases stay unseen) ---------------
ORACLE_DIR="$SCRIPT_DIR/.agentloop/oracle_sealed"
mkdir -p "$ORACLE_DIR"
SEAL="${ORACLE_SEAL:-roman-demo-secret}"
if ! python3 -m agentloop.oracle record \
  --reference "python3 /tmp/ref_roman.py" \
  --inputs /tmp/roman_cases.txt \
  --visible 3 \
  --out "$ORACLE_DIR/roman_oracle.json" \
  --seal "$SEAL"; then
  echo "FAIL: oracle record failed"
  exit 2
fi

# --- Grade the candidate on ALL inputs (visible + held-out) ------------------
if ! python3 -m agentloop.oracle grade \
  --candidate "python3 $SANDBOX/roman.py" \
  --oracle "$ORACLE_DIR/roman_oracle.json" \
  --seal "$SEAL"; then
  echo "VERIFICATION FAILED"
  exit 1
fi
echo "VERIFICATION PASSED"
exit 0
