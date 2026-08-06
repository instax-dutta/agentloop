#!/usr/bin/env python3
"""End-to-end test of the CLI loop using the deterministic mock agent.

Proves: agent writes buggy code -> oracle FAILS -> failure fed back ->
agent retries -> oracle PASSES -> loop stops. No LLM involved.
"""
import argparse
import contextlib as _ctx
import io as _io
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
from agentloop import oracle  # noqa: E402

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


def _clean_plan_artifacts(tasks: int = 3) -> None:
    """Remove per-task state/log/pid/summary/goal files and sandbox dirs left
    behind by parallel plan runs (--run). Safe to call before AND after, so
    stale artifacts from an earlier crashed run can't break absence assertions."""
    for n in range(1, tasks + 1):
        for f in (ROOT / f"agentloop.state.task-{n}.json",
                  ROOT / f"agentloop.log.task-{n}",
                  ROOT / f"agentloop.log.task-{n}.json",
                  ROOT / f"agentloop.pid.task-{n}",
                  ROOT / f"agentloop.pid.task-{n}.json",
                  ROOT / f"agentloop.summary.task-{n}",
                  ROOT / f"agentloop.summary.task-{n}.json",
                  ROOT / f"goal.task-{n}.txt"):
            f.unlink(missing_ok=True)
        shutil.rmtree(ROOT / "sandbox" / f"task-{n}", ignore_errors=True)


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
# ---------------------------------------------------------------------------
# 16. BLOCKED_GOAL_PATTERNS
# ---------------------------------------------------------------------------
_clean_artifacts()
os.environ["BLOCKED_GOAL_PATTERNS"] = "rm -rf:mkfs,dd if="
try:
    agentloop._validate_goal("please rm -rf /tmp")
    assert False, "should exit on blocked goal pattern"
except SystemExit:
    pass
assert agentloop._validate_goal("safe goal") == "safe goal"
os.environ.pop("BLOCKED_GOAL_PATTERNS", None)
print("BLOCKED_GOAL_PATTERNS TEST: PASS")

# ---------------------------------------------------------------------------
# 17. DIRECT MODE CONFIG ALIASES & VERSION
# ---------------------------------------------------------------------------
_clean_artifacts()
os.environ["AGENTLOOP_API_KEY"] = "sk-test-key"
os.environ["AGENTLOOP_BASE_URL"] = "https://custom.api/v1"
os.environ["AGENTLOOP_MODEL"] = "custom-model"
agentloop.read_config()
assert agentloop.API_KEY == "sk-test-key"
assert agentloop.BASE_URL == "https://custom.api/v1"
assert agentloop.MODEL == "custom-model"

os.environ.pop("AGENTLOOP_API_KEY", None)
os.environ.pop("AGENTLOOP_BASE_URL", None)
os.environ.pop("AGENTLOOP_MODEL", None)
os.environ["KILO_API_KEY"] = "kilo-test-key"
agentloop.read_config()
assert agentloop.API_KEY == "kilo-test-key"
assert agentloop.BASE_URL == "https://api.openai.com/v1"
assert agentloop.MODEL == "gpt-4o-mini"
os.environ.pop("KILO_API_KEY", None)
agentloop.read_config()
print("DIRECT MODE CONFIG ALIASES TEST: PASS")

# ---------------------------------------------------------------------------
# 18. CONTAINER ISOLATION FLAGS
# ---------------------------------------------------------------------------
_clean_artifacts()
from agentloop.docker import run_in_docker
assert callable(run_in_docker)
os.environ["USE_DOCKER"] = "1"
agentloop.read_config()
assert agentloop.USE_DOCKER is True
os.environ.pop("USE_DOCKER", None)

os.environ["USE_PODMAN"] = "1"
agentloop.read_config()
assert agentloop.USE_PODMAN is True
os.environ.pop("USE_PODMAN", None)
agentloop.read_config()
print("CONTAINER ISOLATION FLAGS TEST: PASS")

# ---------------------------------------------------------------------------
# 19. CMD_COST SUBCOMMAND
# ---------------------------------------------------------------------------
_clean_artifacts()
STATE.write_text(json.dumps({
    "goal": "cost test", "mode": "cli", "iter": 1, "status": "completed",
    "running_cost": 0.05,
    "cost_breakdown": {
        "running_cost": 0.05, "iterations": 1,
        "by_iter": [{"iter": 1, "preset": "claude", "model": "claude-3-7-sonnet", "cost": 0.05, "input_tokens": 1000, "output_tokens": 500, "is_estimated": False}]
    }
}))
rc_cost = agentloop.cmd_cost(argparse.Namespace())
assert rc_cost == 0
print("CMD_COST SUBCOMMAND TEST: PASS")

# ---------------------------------------------------------------------------
# 20. LOG_JSON STRUCTURED LOGGING
# ---------------------------------------------------------------------------
_clean_artifacts()
agentloop._logger_initialized = False
old_log_json = os.environ.get("LOG_JSON", "")
os.environ["LOG_JSON"] = "true"
agentloop.read_config()
_buf = _io.StringIO()
with _ctx.redirect_stdout(_buf):
    agentloop.log("json test message")
_rec = json.loads(_buf.getvalue().strip())
assert _rec["msg"] == "json test message"
assert "ts" in _rec and _rec["level"] == "info"
os.environ["LOG_JSON"] = old_log_json
agentloop.read_config()
agentloop._logger_initialized = False
print("LOG_JSON STRUCTURED LOGGING TEST: PASS")

# ---------------------------------------------------------------------------
# 21. CMD_EXAMPLES SUBCOMMAND
# ---------------------------------------------------------------------------
_clean_artifacts()
_buf = _io.StringIO()
with _ctx.redirect_stdout(_buf):
    rc_ex = agentloop.cmd_examples(argparse.Namespace())
assert rc_ex == 0
_out = _buf.getvalue()
assert "json-linter" in _out
assert "regex-engine" in _out
assert "api-endpoint" in _out
print("CMD_EXAMPLES SUBCOMMAND TEST: PASS")

# ---------------------------------------------------------------------------
# 22. CMD_DOCTOR SUBCOMMAND
# ---------------------------------------------------------------------------
_clean_artifacts()
old_vcmd = os.environ.get("VERIFY_CMD", "")
os.environ["VERIFY_CMD"] = "true"
rc_doc_ok = agentloop.cmd_doctor(argparse.Namespace(goal=None))
assert rc_doc_ok == 0, f"doctor should be healthy with a verifier set, got rc={rc_doc_ok}"
os.environ["VERIFY_CMD"] = ""
rc_doc_bad = agentloop.cmd_doctor(argparse.Namespace(goal=None))
assert rc_doc_bad != 0, "doctor should flag a missing verifier"
os.environ["VERIFY_CMD"] = old_vcmd
print("CMD_DOCTOR SUBCOMMAND TEST: PASS")

# ---------------------------------------------------------------------------
# 23. COST-AWARE PROMPT BUDGET INJECTION
# ---------------------------------------------------------------------------
_clean_artifacts()
old_max = os.environ.get("MAX_COST_USD", "")
old_est = os.environ.get("ESTIMATED_COST_PER_ITER", "")
os.environ["MAX_COST_USD"] = "1.0"
os.environ["ESTIMATED_COST_PER_ITER"] = "0.10"
agentloop.read_config()
p_crit = agentloop.build_prompt("goal", [], remaining_budget=0.05)
assert "BUDGET CRITICAL" in p_crit, "budget-critical prompt should fire near the cap"
p_ok = agentloop.build_prompt("goal", [], remaining_budget=5.0)
assert "BUDGET CRITICAL" not in p_ok
os.environ["MAX_COST_USD"] = old_max or "0"
os.environ["ESTIMATED_COST_PER_ITER"] = old_est or "0.10"
agentloop.read_config()
print("COST-AWARE PROMPT BUDGET TEST: PASS")

# ---------------------------------------------------------------------------
# 24. PARALLEL PLAN RUNNER (--run with --workers, DAG-aware)
# ---------------------------------------------------------------------------
_clean_artifacts()
_plan = ROOT / "test_plan.md"
_plan.write_text(textwrap.dedent("""\
    # Test plan
    - [ ] Task alpha
    - [ ] Task beta (after: #1)
"""))
old_v2 = os.environ.get("VERIFY_CMD", "")
os.environ["VERIFY_CMD"] = "true"
rc_plan = agentloop.cmd_run_plan(argparse.Namespace(
    run=str(_plan), verify="true", harness=None, agent_cmd=None,
    workers=2, timeout=90))
assert rc_plan == 0, f"parallel plan should pass with a trivial verifier, got rc={rc_plan}"
assert (ROOT / "agentloop.state.task-1.json").exists(), "task-1 state file should exist"
assert (ROOT / "agentloop.state.task-2.json").exists(), "task-2 state file should exist"
assert (ROOT / "sandbox" / "task-1").is_dir(), "task-1 sandbox should exist"
_plan.unlink(missing_ok=True)
_clean_plan_artifacts(2)
os.environ["VERIFY_CMD"] = old_v2
print("PARALLEL PLAN RUNNER TEST: PASS")

# ---------------------------------------------------------------------------
# 25. COST_BREAKDOWN PERSISTENCE (survives mid-loop saves AND finish())
# ---------------------------------------------------------------------------
_clean_artifacts()
_clean_sandbox()
agentloop.run_cli_mode("build a tax calculator (mock test)")
_state = json.loads(STATE.read_text())
_cb = _state.get("cost_breakdown", {})
assert isinstance(_cb, dict) and _cb.get("by_iter"), \
    "cost_breakdown must persist after finish()"
assert _state.get("status") == "completed"
assert len(_cb["by_iter"]) >= 1, "by_iter should record at least one iteration"
print("COST_BREAKDOWN PERSISTENCE TEST: PASS")

# ---------------------------------------------------------------------------
# 26. --serve COST BREAKDOWN CARD (start server, GET /, assert the cost bars)
# ---------------------------------------------------------------------------
_clean_artifacts()
STATE.write_text(json.dumps({
    "goal": "serve test", "mode": "cli", "iter": 3, "status": "running",
    "running_cost": 0.15,
    "cost_breakdown": {
        "running_cost": 0.15, "iterations": 3,
        "by_iter": [
            {"iter": 1, "model": "claude-3-7-sonnet", "cost": 0.05,
             "input_tokens": 1000, "output_tokens": 500, "is_estimated": False},
            {"iter": 2, "model": "claude-3-7-sonnet", "cost": 0.08,
             "input_tokens": 1200, "output_tokens": 600, "is_estimated": False},
            {"iter": 3, "model": "gpt-4o-mini", "cost": 0.02,
             "input_tokens": 800, "output_tokens": 200, "is_estimated": True},
        ],
    },
}))
import threading as _th
import urllib.request as _urlreq
_srv = agentloop.HTTPServer(("127.0.0.1", 0), agentloop._MonitorHandler)
_port = _srv.server_address[1]
_thr = _th.Thread(target=_srv.serve_forever, daemon=True)
_thr.start()
try:
    with _urlreq.urlopen(f"http://127.0.0.1:{_port}/", timeout=10) as _resp:
        assert _resp.status == 200, f"GET / should return 200, got {_resp.status}"
        _html = _resp.read().decode("utf-8")
finally:
    _srv.shutdown()
    _srv.server_close()
    _thr.join(timeout=5)

# The cost breakdown card + one CSS bar per iteration must be present.
assert "Cost Breakdown" in _html, "HTML should include the Cost Breakdown card"
assert _html.count("class='bar-row'") == 3, "one bar-row per iteration expected"
assert _html.count("class='bar-fill'") == 3, "one bar-fill per iteration expected"
assert "width:100%" in _html, "the largest iteration cost should render a full-width bar"
for _label in ("iter 1", "iter 2", "iter 3"):
    assert _label in _html, f"missing bar label {_label!r}"
for _model in ("claude-3-7-sonnet", "gpt-4o-mini"):
    assert _model in _html, f"missing model in By-model breakdown: {_model!r}"
assert "$0.0800" in _html, "per-iteration costs should be shown next to the bars"
assert "(est)" in _html, "estimated iterations should be flagged"
# The direct render helper must agree with what the server actually serves.
_page = agentloop._render_status_page()
assert "Cost Breakdown" in _page and "class='bar-fill'" in _page
print("SERVE COST BREAKDOWN CARD TEST: PASS (HTTP GET /)")

# ---------------------------------------------------------------------------
# 27. PARALLEL PLAN: DOWNSTREAM TASKS SKIPPED WHEN A DEPENDENCY FAILS
# ---------------------------------------------------------------------------
_clean_artifacts()
_clean_plan_artifacts(3)  # clear stale task files first so absence asserts are sound
_plan_fail = ROOT / "test_plan_fail.md"
_plan_fail.write_text(textwrap.dedent("""\
    # Test plan
    - [ ] Task alpha
    - [ ] Task beta (after: #1)
    - [ ] Task gamma (after: #2)
"""))
_buf27 = _io.StringIO()
with _ctx.redirect_stdout(_buf27):
    rc_fail = agentloop.cmd_run_plan(argparse.Namespace(
        run=str(_plan_fail), verify="false", harness=None, agent_cmd=None,
        workers=3, timeout=180))
_out27 = _buf27.getvalue()
assert rc_fail != 0, "a plan with a failing dependency must not exit 0"
assert "❌ [FAILED] Task 1:" in _out27, "task 1 should run and fail"
assert "⏭️ [SKIPPED] Task 2:" in _out27, "task 2 must be skipped (depends on failed #1)"
assert "⏭️ [SKIPPED] Task 3:" in _out27, "task 3 must be skipped transitively (depends on #2)"
# Task 1 actually ran to failure: state file + sandbox exist. With verify="false"
# and MAX_ITERS=5 (set at import), task 1 burns all iterations -> status exhausted.
_t1_state = json.loads((ROOT / "agentloop.state.task-1.json").read_text())
assert _t1_state.get("status") == "exhausted", "task 1 should have run to exhaustion"
assert (ROOT / "sandbox" / "task-1").is_dir(), "task 1 sandbox should exist"
# Downstream tasks must NEVER have started: no state file, no sandbox dir
for _tid in ("task-2", "task-3"):
    assert not (ROOT / f"agentloop.state.{_tid}.json").exists(), \
        f"{_tid} must be skipped, not run (state file must not exist)"
    assert not (ROOT / "sandbox" / _tid).exists(), \
        f"{_tid} must be skipped, not run (sandbox must not exist)"
_plan_fail.unlink(missing_ok=True)
_clean_plan_artifacts(3)
print("PARALLEL PLAN DEPENDENCY-SKIP TEST: PASS")

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
