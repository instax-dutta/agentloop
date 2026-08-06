#!/usr/bin/env bash
# Verification oracle for the git-history-rewriter example.
# Fixture-based oracle: builds a real git repo with multiple authors and
# commits, runs the agent's rewriter against it, then asserts every commit
# author is normalized while topology/messages are preserved.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/sandbox" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
SANDBOX="${AGENTLOOP_SANDBOX:-$PROJECT_ROOT/sandbox}"
fail=0

if [ ! -f "$SANDBOX/git_author_fixer.py" ]; then
  echo "FAIL: $SANDBOX/git_author_fixer.py not found — has the agent created it?"
  exit 2
fi

FIXTURE="/tmp/agentloop_fixture_repo"
rm -rf "$FIXTURE"
git init -q "$FIXTURE"
cd "$FIXTURE"
git config user.name "Alice Original"
git config user.email "alice@corp.example"
echo "v1" > file.txt && git add file.txt
git commit -qm "initial commit"
git config user.name "Bob Original"
git config user.email "bob@corp.example"
echo "v2" >> file.txt && git add file.txt
git commit -qm "second change"
git config user.name "Carol Original"
git config user.email "carol@corp.example"
echo "v3" >> file.txt && git add file.txt
git commit -qm "third change"
git branch -m main 2>/dev/null || true
EXPECTED_LOG="$(git log --format='%s')"

# Run the agent's rewriter against the fixture
python3 "$SANDBOX/git_author_fixer.py" "$FIXTURE" || {
  echo "FAIL: rewriter exited non-zero"
  exit 1
}

cd "$FIXTURE"
AUTHORS="$(git log --format='%an <%ae>' | sort -u)"
if [ "$AUTHORS" = "AgentLoop <agentloop@local>" ]; then
  echo "PASS: all commit authors normalized to AgentLoop"
else
  echo "FAIL: authors are: $AUTHORS"
  fail=1
fi

NEW_LOG="$(git log --format='%s')"
if [ "$NEW_LOG" = "$EXPECTED_LOG" ]; then
  echo "PASS: commit messages + order preserved"
else
  echo "FAIL: history topology changed"
  echo "  expected: $EXPECTED_LOG"
  echo "  got     : $NEW_LOG"
  fail=1
fi

if [ "$(cat file.txt)" != "v1
v2
v3" ]; then
  echo "FAIL: file contents changed by the rewrite"
  fail=1
else
  echo "PASS: file contents unchanged"
fi

rm -rf "$FIXTURE"

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
