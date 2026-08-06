#!/usr/bin/env bash
# Verification oracle for the rpn-calculator community verifier.
#
# Pattern: property-based (tag: property-based). A seeded generator emits pairs
# of RPN expressions that are algebraically guaranteed to evaluate to the same
# integer (commutativity, associativity, distributivity, and identity laws).
# The verifier runs the candidate on both sides and asserts the outputs agree
# — no reference implementation, no expected values: the invariant IS the
# oracle. A small fixed edge set anchors the error semantics (division by zero,
# stack underflow, malformed tokens) that pure invariants can't express.
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

if [ ! -f "$SANDBOX/calc.py" ]; then
  echo "FAIL: $SANDBOX/calc.py not found — has the agent created it?"
  exit 2
fi

python3 - "$SANDBOX/calc.py" <<'PY'
import random
import subprocess
import sys

candidate = sys.argv[1]

# --- 1. Seeded property-pair generator ---------------------------------------
rng = random.Random(1337)


def rnd():
    return rng.randint(-9, 9)


# name, arity, builder -> (left_expr, right_expr). Every pair is exactly equal
# under integer arithmetic, so ANY correct evaluator must agree on both sides.
props = [
    ("comm-add", 2, lambda a, b: (f"{a} {b} +", f"{b} {a} +")),
    ("comm-mul", 2, lambda a, b: (f"{a} {b} *", f"{b} {a} *")),
    ("assoc-add", 3, lambda a, b, c: (f"{a} {b} + {c} +", f"{a} {b} {c} + +")),
    ("assoc-mul", 3, lambda a, b, c: (f"{a} {b} * {c} *", f"{a} {b} {c} * *")),
    ("distrib", 3, lambda a, b, c: (f"{a} {b} + {c} *",
                                    f"{a} {c} * {b} {c} * +")),
    ("ident-add", 1, lambda a: (f"{a} 0 +", f"{a}")),
    ("ident-add-l", 1, lambda a: (f"0 {a} +", f"{a}")),
    ("ident-mul", 1, lambda a: (f"{a} 1 *", f"{a}")),
    ("zero-ann", 1, lambda a: (f"{a} 0 *", "0")),
    ("sub-zero", 1, lambda a: (f"{a} 0 -", f"{a}")),
    ("div-one", 1, lambda a: (f"{a} 1 /", f"{a}")),
    ("self-div", 1, lambda a: (f"{a} {a} /", "1") if a != 0 else None),
]

left, right = [], []
for _ in range(80):
    name, arity, build = rng.choice(props)
    pair = build(*[rnd() for _ in range(arity)])
    if pair is not None:
        left.append(pair[0])
        right.append(pair[1])

# --- 2. Property checks: both sides must evaluate identically ----------------
r1 = subprocess.run(["python3", candidate], input="\n".join(left) + "\n",
                    capture_output=True, text=True)
r2 = subprocess.run(["python3", candidate], input="\n".join(right) + "\n",
                    capture_output=True, text=True)
for rc, side, err in ((r1.returncode, "left", r1.stderr),
                      (r2.returncode, "right", r2.stderr)):
    if rc != 0:
        print(f"FAIL: candidate crashed on the {side} property set "
              f"(exit {rc}): {err.strip()[:200]}")
        sys.exit(1)
out1, out2 = r1.stdout.splitlines(), r2.stdout.splitlines()
if len(out1) != len(left) or len(out2) != len(right):
    print(f"FAIL: expected {len(left)} result lines per side, got "
          f"{len(out1)} and {len(out2)} — wrong line count")
    sys.exit(1)
for i, (e1, e2, o1, o2) in enumerate(zip(left, right, out1, out2)):
    if o1 != o2:
        print(f"FAIL property pair {i}: algebraically-equal expressions "
              f"disagree:")
        print(f"  left:  {e1!r} -> {o1!r}")
        print(f"  right: {e2!r} -> {o2!r}")
        sys.exit(1)
print(f"{len(left)} property pairs: all algebraic invariants hold")

# --- 3. Empty input produces no output; blank lines are skipped --------------
r = subprocess.run(["python3", candidate], input="", capture_output=True,
                   text=True)
if r.returncode != 0 or r.stdout != "":
    print(f"FAIL: empty input must produce no output (exit {r.returncode}, "
          f"stdout {r.stdout!r})")
    sys.exit(1)
r = subprocess.run(["python3", candidate], input="2 3 +\n\n5 1 2 + *\n",
                   capture_output=True, text=True)
if r.returncode != 0 or r.stdout != "5\n15\n":
    print(f"FAIL: blank lines must be skipped; expected '5\\n15\\n', got "
          f"{r.stdout!r} (exit {r.returncode})")
    sys.exit(1)

# --- 4. Fixed edge semantics (anchors invariants can't express) ---------------
edges = [
    ("2 3 +", "5"),
    ("9 3 -", "6"),
    ("9 3 /", "3"),
    ("7 2 /", "3"),
    ("-7 2 /", "-3"),
    ("7 -2 /", "-3"),
    ("-7 -2 /", "3"),
    ("0 5 /", "0"),
    ("2 3 * 4 +", "10"),
    ("5 1 2 + *", "15"),
    ("1 0 /", "ERROR"),      # division by zero
    ("+", "ERROR"),          # stack underflow
    ("1 +", "ERROR"),        # stack underflow
    ("foo bar", "ERROR"),    # malformed tokens
    ("1 2", "ERROR"),        # leftover operands
    ("1 2 3 +", "ERROR"),    # leftover operands
]
r = subprocess.run(["python3", candidate],
                   input="\n".join(e for e, _ in edges) + "\n",
                   capture_output=True, text=True)
if r.returncode != 0:
    print(f"FAIL: candidate crashed on the edge set "
          f"(exit {r.returncode}): {r.stderr.strip()[:200]}")
    sys.exit(1)
got = r.stdout.splitlines()
if len(got) != len(edges):
    print(f"FAIL: edge set expected {len(edges)} result lines, got {len(got)}")
    sys.exit(1)
for (expr, want), g in zip(edges, got):
    if g != want:
        print(f"FAIL edge {expr!r}: expected {want!r}, got {g!r}")
        sys.exit(1)
print(f"{len(edges)} edge cases: exact error semantics hold")
PY
rc=$?

if [ "$rc" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
