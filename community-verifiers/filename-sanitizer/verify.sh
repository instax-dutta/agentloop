#!/usr/bin/env bash
# Verification oracle for the filename-sanitizer community verifier.
#
# Pattern: fixture + post-conditions (tag: fixture). The verifier builds a
# realistic directory tree in a temp dir, runs the agent's sanitize.py against
# a COPY of it (the sandbox itself is never touched), and asserts the exact
# post-conditions — including adversarial cases (hidden files, collisions,
# deep nesting that forces bottom-up renaming).
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
fail=0

if [ ! -f "$SANDBOX/sanitize.py" ]; then
  echo "FAIL: $SANDBOX/sanitize.py not found — has the agent created it?"
  exit 2
fi

TMPDIR_VERIFY="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_VERIFY"' EXIT

# --- 1. Build the fixture tree (fixed, deterministic) -----------------------
FIXTURE="$TMPDIR_VERIFY/fixture"
WORK="$TMPDIR_VERIFY/work"
mkdir -p "$FIXTURE/docs/sub folder" "$FIXTURE/media"

touch "$FIXTURE/my notes.txt"          # space -> underscore
touch "$FIXTURE/todo list.md"          # space -> underscore
touch "$FIXTURE/docs/read me.txt"      # recursive nested file
touch "$FIXTURE/docs/sub folder/deep file.log"  # deep nesting
touch "$FIXTURE/.hidden file"          # hidden -> must NOT be touched
touch "$FIXTURE/a b.txt"               # collides with a_b.txt below
touch "$FIXTURE/a_b.txt"               # collision target must survive
touch "$FIXTURE/plain.txt"             # control: no spaces
touch "$FIXTURE/media/photo.jpg"       # control: no spaces

# --- 2. Work on a COPY so the sandbox is never mutated ----------------------
cp -R "$FIXTURE" "$WORK"

# --- 3. Run the candidate against the copy ----------------------------------
if ! python3 "$SANDBOX/sanitize.py" "$WORK"; then
  echo "FAIL: sanitize.py exited non-zero"
  fail=1
fi

check() {
  local desc="$1" path="$2" expect="$3"
  if [ "$expect" = "yes" ] && [ ! -e "$WORK/$path" ]; then
    echo "FAIL: $desc — expected to exist: $path"
    fail=1
  elif [ "$expect" = "no" ] && [ -e "$WORK/$path" ]; then
    echo "FAIL: $desc — expected gone, still present: $path"
    fail=1
  fi
}

# --- 4. Assert post-conditions ----------------------------------------------
check "space -> underscore"        "my_notes.txt"                  yes
check "space -> underscore"        "todo_list.md"                  yes
check "recursive nested file"      "docs/read_me.txt"              yes
check "nested dir renamed"         "docs/sub_folder"               yes
check "deep nesting"               "docs/sub_folder/deep_file.log" yes
check "collision got suffix"       "a_b_2.txt"                     yes

check "old name gone"              "my notes.txt"                  no
check "old name gone"              "todo list.md"                  no
check "old dir gone"               "docs/sub folder"               no

check "control untouched"          "plain.txt"                     yes
check "control untouched"          "media/photo.jpg"               yes
check "hidden untouched"           ".hidden file"                  yes
check "collision original kept"    "a_b.txt"                       yes

# --- 5. No non-hidden name may still contain a space -------------------------
if find "$WORK" -mindepth 1 -name '* *' ! -name '.*' | grep -q .; then
  echo "FAIL: leftover spaces in non-hidden names:"
  find "$WORK" -mindepth 1 -name '* *' ! -name '.*'
  fail=1
fi

# --- 6. No spurious files may appear (the tree must contain exactly the ------
# ---    fixture's 8 top-level entries after a correct run) ---------------------
top_count="$(find "$WORK" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
if [ "$top_count" -ne 8 ]; then
  echo "FAIL: unexpected top-level entries (expected 8, got $top_count):"
  find "$WORK" -mindepth 1 -maxdepth 1
  fail=1
fi

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
