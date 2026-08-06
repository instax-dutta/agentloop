#!/usr/bin/env bash
# Verification oracle for the uniq-reimplementation community verifier.
#
# Pattern: behavior-equivalence (tag: behavior-equivalence). Generates random
# line batches with deliberate duplicate runs and compares the agent's uniq.py
# stdout byte-for-byte against a reference implementation — with and without
# the -c flag — on every batch. Correctness is proven by equivalence, not by
# eyeballing example outputs.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Locate the project root: the nearest ancestor containing a sandbox/ dir.
# Handles any nesting depth — verify.sh next to sandbox/, the whole folder
# next to sandbox/, or in-repo community-verifiers/<name>/.
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

if [ ! -f "$SANDBOX/uniq.py" ]; then
  echo "FAIL: $SANDBOX/uniq.py not found — has the agent created it?"
  exit 2
fi

# --- Reference implementation (this DEFINES the exact spec) -----------------
cat > /tmp/ref_uniq.py <<'PY'
import sys


def uniq(lines, count):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        j = i + 1
        while j < n and lines[j] == lines[i]:
            j += 1
        if count:
            out.append(f"{j - i} {lines[i]}")
        else:
            out.append(lines[i])
        i = j
    return out


if __name__ == "__main__":
    data = sys.stdin.read()
    if data.endswith("\n"):
        data = data[:-1]
    lines = data.split("\n")
    out = uniq(lines, "-c" in sys.argv[1:])
    if out:
        sys.stdout.write("\n".join(out) + "\n")
PY

# --- Deterministic test batches (seeded) --------------------------------------
python3 - <<'PY'
import json
import random

rng = random.Random(1337)
words = ["foo", "bar", "", "  spaced  ", "café", "héllo", "a", "tab\there",
         "end ", "AAA", "   ", "ümlaut", "日本語"]
batches = []
for _ in range(40):
    n = rng.randint(0, 14)
    lines = []
    for _ in range(n):
        if lines and rng.random() < 0.35:
            lines.append(lines[-1])  # force a consecutive duplicate run
        else:
            lines.append(rng.choice(words))
    batches.append(lines)
# Explicit edge cases
batches += [
    [],
    ["a"],
    ["a", "a"],
    ["a", "a", "a"],
    ["a", "b", "a"],            # non-adjacent repeats must NOT merge
    [""] * 4,                    # blank lines dedup
    [" ", " ", ""],              # whitespace-only != blank
    ["x", "x", "y", "x"],
    ["café", "café", "café"],
    ["\t", "\t", "a"],
    ["end ", "end "],
]
json.dump(batches, open("/tmp/uniq_batches.json", "w"))
print(f"generated {len(batches)} batches", flush=True)
PY

# --- Behavior-equivalence: candidate vs reference on every batch -------------
python3 - "$SANDBOX/uniq.py" <<'PY'
import json
import subprocess
import sys

candidate = sys.argv[1]
batches = json.load(open("/tmp/uniq_batches.json"))

for i, lines in enumerate(batches):
    data = "\n".join(lines)
    for flag in ("", "-c"):
        args = [flag] if flag else []
        ref = subprocess.run(["python3", "/tmp/ref_uniq.py"] + args,
                             input=data, capture_output=True, text=True)
        got = subprocess.run(["python3", candidate] + args,
                             input=data, capture_output=True, text=True)
        if got.returncode != 0:
            print(f"FAIL batch {i} flag={flag or '(none)'}: candidate crashed "
                  f"(exit {got.returncode}): {got.stderr.strip()[:200]}")
            sys.exit(1)
        if ref.stdout != got.stdout:
            print(f"FAIL batch {i} flag={flag or '(none)'}: output mismatch")
            print(f"  input:    {data[:120]!r}")
            print(f"  expected: {ref.stdout[:120]!r}")
            print(f"  got:      {got.stdout[:120]!r}")
            sys.exit(1)

print(f"all {len(batches)} batches x 2 modes MATCH", flush=True)
PY
rc=$?

if [ "$rc" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
