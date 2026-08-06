#!/usr/bin/env bash
# Verification oracle for the sql-query-rewriter example.
# Behavior-equivalence oracle: runs the ORIGINAL query and the agent's REWRITTEN
# query against a real SQLite database and compares result sets row-for-row.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/sandbox" ]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
SANDBOX="${AGENTLOOP_SANDBOX:-$PROJECT_ROOT/sandbox}"
fail=0

if [ ! -f "$SANDBOX/sql_rewriter.py" ]; then
  echo "FAIL: $SANDBOX/sql_rewriter.py not found — has the agent created it?"
  exit 2
fi

python3 - "$SANDBOX/sql_rewriter.py" <<'PY'
import sqlite3, subprocess, sys

REWRITER = sys.argv[1]
DB = "/tmp/rewriter_fixture.db"

conn = sqlite3.connect(DB)
conn.executescript(
    """
    DROP TABLE IF EXISTS users;
    DROP TABLE IF EXISTS orders;
    CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);
    CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL);
    INSERT INTO users VALUES (1,'alice',30),(2,'bob',25),(3,'carol',41),(4,'dana',18);
    INSERT INTO orders VALUES (1,1,10.5),(2,1,5.0),(3,3,99.99),(4,2,1.25),(5,2,2.50),(6,4,0.0);
    """
)

QUERIES = [
    "SELECT * FROM users",
    "SELECT name FROM users WHERE age > 25",
    "SELECT name, total FROM users JOIN orders ON users.id = orders.user_id",
    "SELECT COUNT(*) FROM orders",
    "SELECT name FROM users WHERE id IN (1, 3)",
    "SELECT user_id, SUM(total) AS s FROM orders GROUP BY user_id ORDER BY user_id",
    "SELECT name FROM users WHERE age BETWEEN 20 AND 40",
    "SELECT name FROM users ORDER BY age DESC",
]

fail = 0
for i, q in enumerate(QUERIES, start=1):
    r = subprocess.run([sys.executable, REWRITER], input=q, capture_output=True, text=True, timeout=20)
    rewritten = (r.stdout or "").strip()
    if not rewritten:
        print(f"FAIL: query {i} produced empty rewrite for: {q}")
        fail = 1
        continue
    try:
        orig = conn.execute(q).fetchall()
        new = conn.execute(rewritten).fetchall()
    except Exception as e:
        print(f"FAIL: query {i} rewrite is not valid SQL ({e}): {rewritten}")
        fail = 1
        continue
    if orig != new:
        print(f"FAIL: query {i} results differ.")
        print(f"  original : {q}")
        print(f"  rewritten: {rewritten}")
        print(f"  orig rows: {orig}")
        print(f"  new rows : {new}")
        fail = 1
    else:
        print(f"PASS: query {i} equivalent")

conn.close()
sys.exit(fail)
PY
rc=$?
[ "$rc" -ne 0 ] && fail=1

if [ "$fail" -ne 0 ]; then echo "VERIFICATION FAILED"; exit 1; fi
echo "VERIFICATION PASSED"
exit 0
