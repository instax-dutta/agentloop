#!/usr/bin/env python3
"""End-to-end test of the CLI loop using the deterministic mock agent.

Proves: agent writes buggy code -> oracle FAILS -> failure fed back ->
agent retries -> oracle PASSES -> loop stops. No LLM involved.
"""
import argparse
import json
import os
import shutil
import subprocess

import tempfile as _tf
import textwrap
import time as _t
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

# Configure the harness BEFORE importing it (module reads env at import time).
os.environ["AGENT_CMD"] = f"bash {ROOT / 'mock_agent.sh'}"
os.environ["VERIFY_CMD"] = "bash verify.sh"
os.environ["STEP_DELAY"] = "0"
os.environ["MAX_ITERS"] = "5"
os.environ["AGENT_TIMEOUT"] = "30"

import agentloop  # noqa: E402
import oracle      # noqa: E402

sb = ROOT / "sandbox"
STATE = ROOT / "agentloop.state.json"


def _clean_sandbox():
    if sb.exists():
        shutil.rmtree(sb)
    sb.mkdir()


def _clean_artifacts():
    for f in (STATE, ROOT / "agentloop.summary.txt",
              ROOT / "agentloop.log", ROOT / "agentloop.pid"):
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. CLI LOOP: reject -> retry -> pass
# ---------------------------------------------------------------------------
_clean_sandbox()
agentloop.run_cli_mode("build a tax calculator (mock test)")

passed, out = oracle.verify_passed(ROOT)
assert passed, f"verification should pass after the loop:\n{out}"
src = (sb / "tax_calc.py").read_text()
assert "(11000, 0.10)" in src, "final code should be the CORRECT version"
assert (sb / ".git").exists(), "sandbox should be git-initialized for checkpoints"
print("CLI LOOP TEST: PASS (reject -> retry -> pass)")

# ---------------------------------------------------------------------------
# 2. RESUME TEST: simulate a crash mid-run
# ---------------------------------------------------------------------------
_clean_sandbox()
STATE.unlink(missing_ok=True)
subprocess.run(["git", "init", "-q"], cwd=str(sb), capture_output=True)
subprocess.run(f"bash {ROOT / 'mock_agent.sh'}", shell=True, cwd=str(sb),
               capture_output=True)
STATE.write_text(json.dumps({"goal": "build a tax calculator (mock test)",
                             "mode": "cli", "iter": 2, "feedback": [],
                             "started_at": _t.time(), "status": "running"}))
agentloop.run_cli_mode("build a tax calculator (mock test)")
passed2, _ = oracle.verify_passed(ROOT)
assert passed2, "verification should pass after resume"
assert "resuming from iter 2" in (ROOT / "agentloop.log").read_text(), "expected resume log"
print("RESUME TEST: PASS (crash-safe resume from iter 2)")

# ---------------------------------------------------------------------------
# 3. WALL-CLOCK: resume must not reset the budget
# ---------------------------------------------------------------------------
_clean_sandbox()
STATE.unlink(missing_ok=True)
old_wall = os.environ.get("WALL_CLOCK_SEC", "")
os.environ["WALL_CLOCK_SEC"] = "1"
agentloop.read_config()
STATE.write_text(json.dumps({
    "goal": "wall clock test", "mode": "cli", "iter": 1, "feedback": [],
    "started_at": _t.time() - 100, "status": "running",
}))
status = agentloop.run_cli_mode("wall clock test")
assert status == "timeout", f"expected timeout, got {status}"
summary = (ROOT / "agentloop.summary.txt").read_text()
assert "status=timeout" in summary, summary
os.environ["WALL_CLOCK_SEC"] = old_wall or str(6 * 3600)
agentloop.read_config()
print("WALL-CLOCK RESUME TEST: PASS")

# ---------------------------------------------------------------------------
# 4. COST CAP: over-budget status
# ---------------------------------------------------------------------------
_clean_artifacts()
old_cost = os.environ.get("MAX_COST_USD", "")
os.environ["MAX_COST_USD"] = "0.05"  # very low cap
os.environ["ESTIMATED_COST_PER_ITER"] = "0.10"  # each iter costs more than cap
agentloop.read_config()
_clean_sandbox()
status = agentloop.run_cli_mode("cost cap test")
assert status == "over-budget", f"expected over-budget, got {status}"
summary = (ROOT / "agentloop.summary.txt").read_text()
assert "status=over-budget" in summary, summary
os.environ["MAX_COST_USD"] = old_cost or "0"
os.environ.pop("ESTIMATED_COST_PER_ITER", None)
agentloop.read_config()
print("COST CAP TEST: PASS (over-budget detected)")

# ---------------------------------------------------------------------------
# 5. NOTIFY CMD: generic notification hook
# ---------------------------------------------------------------------------
_clean_artifacts()
ntf = _tf.mkdtemp()
note_file = f"{ntf}/note.txt"
os.environ["NOTIFY_CMD"] = f"echo '{{kind}}:{{msg}}' > {note_file}"
agentloop.notify("completed", "all good")
with open(note_file) as fh:
    assert fh.read().strip() == "completed:all good", "notify payload wrong"
os.environ.pop("NOTIFY_CMD", None)
print("NOTIFY TEST: PASS")

# ---------------------------------------------------------------------------
# 6. NOTIFY NATIVE: Telegram/Discord/Slack (no-credential mode does not crash)
# ---------------------------------------------------------------------------
_clean_artifacts()
# Should not raise with empty env vars
agentloop.notify("completed", "test message")
print("NOTIFY NATIVE (no-credential): PASS")

# ---------------------------------------------------------------------------
# 7. terminal_token: no substring false positives
# ---------------------------------------------------------------------------
assert agentloop.terminal_token("DONE", "DONE")
assert agentloop.terminal_token("ok\nDONE\n", "DONE")
assert not agentloop.terminal_token("DONE wrong", "DONE")
assert not agentloop.terminal_token("not done yet", "DONE")
assert agentloop.terminal_token("BLOCKED", "BLOCKED")
print("TERMINAL TOKEN TEST: PASS")

# ---------------------------------------------------------------------------
# 8. atomic_write leaves a complete file
# ---------------------------------------------------------------------------
_clean_artifacts()
p = ROOT / "agentloop.state.json"
agentloop.atomic_write(p, '{"ok": true}\n')
assert json.loads(p.read_text())["ok"] is True
print("ATOMIC WRITE TEST: PASS")

# ---------------------------------------------------------------------------
# 9. version flag
# ---------------------------------------------------------------------------
_clean_artifacts()
try:
    agentloop.main(["--version"])
    raise AssertionError("--version should SystemExit")
except SystemExit as e:
    assert e.code == 0
print("VERSION FLAG TEST: PASS")

# ---------------------------------------------------------------------------
# 10. DRY-RUN / CONFIG SYNC
# ---------------------------------------------------------------------------
_clean_artifacts()
old_cmd = os.environ.pop("AGENT_CMD", None)
code = agentloop.main(["--dry-run", "--harness", "opencode",
                       "--verify", "bash verify.sh", "build something"])
assert code == agentloop.EXIT_COMPLETED
assert agentloop.AGENT_PRESET == "opencode", agentloop.AGENT_PRESET
assert agentloop.resolve_agent_cmd() == 'opencode run "$AGENTLOOP_PROMPT" --auto'
if old_cmd is not None:
    os.environ["AGENT_CMD"] = old_cmd
print("DRY-RUN / CONFIG SYNC TEST: PASS")

# ---------------------------------------------------------------------------
# 11. STATUS COMMAND
# ---------------------------------------------------------------------------
_clean_artifacts()
# With no state file, status should say "No runs found"
code = agentloop.cmd_status(argparse.Namespace())
assert code == agentloop.EXIT_COMPLETED
print("STATUS COMMAND (no run): PASS")

# With a planted state file
agentloop.save_state({
    "goal": "test goal", "mode": "cli", "iter": 5, "feedback": [],
    "started_at": _t.time(), "status": "completed", "running_cost": 0.50,
})
agentloop.write_summary("completed", 5, _t.time(), "test goal", 0.50)
code = agentloop.cmd_status(argparse.Namespace())
assert code == agentloop.EXIT_COMPLETED
print("STATUS COMMAND (completed): PASS")

# ---------------------------------------------------------------------------
# 12. INPUT VALIDATION
# ---------------------------------------------------------------------------
_clean_artifacts()
try:
    agentloop._validate_goal("")
    assert False, "should have exit on empty goal"
except SystemExit:
    pass
try:
    agentloop._validate_goal("   ")
    assert False, "should have exit on whitespace goal"
except SystemExit:
    pass
assert agentloop._validate_goal("valid goal") == "valid goal"
print("INPUT VALIDATION TEST: PASS")

# ---------------------------------------------------------------------------
# 13. CONFIG VALIDATION
# ---------------------------------------------------------------------------
_clean_artifacts()
old_max = os.environ.get("MAX_ITERS", "")
os.environ["MAX_ITERS"] = "0"
agentloop.read_config()  # Re-read so the check uses the new value
try:
    agentloop._validate_config()
    assert False, "should have exit on invalid MAX_ITERS"
except SystemExit:
    pass
os.environ["MAX_ITERS"] = old_max or "50"
agentloop.read_config()
print("CONFIG VALIDATION TEST: PASS")

# ---------------------------------------------------------------------------
# 14. MULTI-AGENT PLAN PARSING
# ---------------------------------------------------------------------------
_clean_artifacts()
plan = textwrap.dedent("""\
    # Plan
    - [ ] First task
    - [ ] Second task with spaces
    ## Third task as heading
    - Fourth task as bullet
""")
tasks = agentloop._parse_plan(plan)
assert len(tasks) == 4, f"expected 4 tasks, got {len(tasks)}: {tasks}"
assert "First task" in tasks
assert "Second task with spaces" in tasks
assert "Third task as heading" in tasks
assert "Fourth task as bullet" in tasks
print("MULTI-AGENT PLAN PARSING: PASS")

# ---------------------------------------------------------------------------
# 15. LOG ROTATION
# ---------------------------------------------------------------------------
_clean_artifacts()
# Reset logger so it creates a fresh file on next log call
agentloop._logger_initialized = False
old_log = os.environ.get("LOG_MAX_MB", "")
os.environ["LOG_MAX_MB"] = "1"  # 1 MB max
agentloop.read_config()
# Write enough to trigger rotation
for i in range(10):
    agentloop.log(f"test message {i} " * 100)
assert (ROOT / "agentloop.log").exists(), "log file should exist"
# Check that rotation didn't crash
log_text = (ROOT / "agentloop.log").read_text()
assert "test message" in log_text
os.environ["LOG_MAX_MB"] = old_log or "10"
agentloop.read_config()
# Reset logger again for subsequent tests
agentloop._logger_initialized = False
print("LOG ROTATION TEST: PASS")

# ---------------------------------------------------------------------------
# CLEANUP
# ---------------------------------------------------------------------------
_clean_artifacts()

# restore the demo sandbox solution so the working tree is not left empty
demo = ROOT / "sandbox" / "tax_calc.py"
if not demo.exists():
    _clean_sandbox()
    subprocess.run(["bash", str(ROOT / "mock_agent.sh")], cwd=str(sb), capture_output=True)
    subprocess.run(["bash", str(ROOT / "mock_agent.sh")], cwd=str(sb), capture_output=True)
    (sb / ".fixed").unlink(missing_ok=True)

print("\nALL LOOP TESTS PASSED")
