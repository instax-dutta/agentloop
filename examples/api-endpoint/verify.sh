#!/usr/bin/env bash
# Verification oracle for the api-endpoint example.
# Integration oracle: boots the agent's server, probes it over HTTP with
# urllib, asserts status codes + JSON bodies, then shuts it down. Stdlib-only
# (the FastAPI/pytest/httpx equivalent is noted in README.md).
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/sandbox" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
SANDBOX="${AGENTLOOP_SANDBOX:-$PROJECT_ROOT/sandbox}"
PORT="${AGENTLOOP_TEST_PORT:-8765}"
fail=0

if [ ! -f "$SANDBOX/app.py" ]; then
  echo "FAIL: $SANDBOX/app.py not found — has the agent created it?"
  exit 2
fi

cd "$SANDBOX"
python3 app.py >/tmp/app.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

# Wait for the server to come up (stdlib-only, no curl)
python3 - "$PORT" <<'PY'
import sys, time, urllib.request
port = int(sys.argv[1])
for _ in range(20):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
        sys.exit(0)
    except Exception:
        time.sleep(0.25)
sys.exit(1)
PY
if [ $? -ne 0 ]; then
  echo "FAIL: server did not come up (see /tmp/app.log)"
  kill $SRV 2>/dev/null
  exit 1
fi

python3 - "$PORT" <<'PY'
import json, sys, urllib.request, urllib.error

port = int(sys.argv[1])
base = f"http://127.0.0.1:{port}"
fail = 0

def get(path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

status, body = get("/health")
if status != 200 or json.loads(body).get("status") != "ok":
    print(f"FAIL: /health -> {status} {body[:120]}")
    fail = 1
else:
    print("PASS: /health returns ok")

status, body = get("/items/7")
if status != 200 or json.loads(body) != {"id": 7, "name": "item-7"}:
    print(f"FAIL: /items/7 -> {status} {body[:120]}")
    fail = 1
else:
    print("PASS: /items/7 returns item-7")

status, body = get("/items/999")
if status != 404:
    print(f"FAIL: /items/999 -> {status} (expected 404) {body[:120]}")
    fail = 1
else:
    print("PASS: /items/999 returns 404")

status, body = get("/nope")
if status != 404:
    print(f"FAIL: /nope -> {status} (expected 404)")
    fail = 1
else:
    print("PASS: unknown path returns 404")

sys.exit(fail)
PY
rc=$?
[ "$rc" -ne 0 ] && fail=1

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
