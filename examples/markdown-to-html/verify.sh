#!/usr/bin/env bash
# Verification oracle for the markdown-to-html example.
# Golden-file comparison: 8 fixed markdown snippets with hand-verified HTML,
# compared character-for-character against the agent's converter.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/sandbox" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
SANDBOX="${AGENTLOOP_SANDBOX:-$PROJECT_ROOT/sandbox}"
fail=0

if [ ! -f "$SANDBOX/md2html.py" ]; then
  echo "FAIL: $SANDBOX/md2html.py not found — has the agent created it?"
  exit 2
fi

check_golden() {
  local name="$1" input="$2" expected="$3"
  local got
  got=$(printf '%s' "$input" | python3 "$SANDBOX/md2html.py" 2>/dev/null || true)
  if [ "$got" != "$expected" ]; then
    echo "FAIL: $name"
    echo "  expected: $(printf '%s' "$expected" | head -c 200)"
    echo "  got     : $(printf '%s' "$got" | head -c 200)"
    fail=1
  else
    echo "PASS: $name"
  fi
}

check_golden "heading" \
  "# Hello" \
  "<h1>Hello</h1>"

check_golden "subheading" \
  "## Section" \
  "<h2>Section</h2>"

check_golden "paragraph" \
  "plain text here" \
  "<p>plain text here</p>"

check_golden "bold+code" \
  "use **bold** and \`code\`" \
  "<p>use <strong>bold</strong> and <code>code</code></p>"

check_golden "list" \
  "- one
- two
- three" \
  "<ul><li>one</li><li>two</li><li>three</li></ul>"

check_golden "escaping" \
  "a < b & c" \
  "<p>a &lt; b &amp; c</p>"

check_golden "mixed blocks" \
  "# Title

some body

- item" \
  "<h1>Title</h1>

<p>some body</p>

<ul><li>item</li></ul>"

check_golden "empty" \
  "" \
  ""

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
