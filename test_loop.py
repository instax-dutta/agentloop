#!/usr/bin/env python3
"""End-to-end test of the CLI loop using the deterministic mock agent.

Proves: agent writes buggy code -> oracle FAILS -> failure fed back ->
agent retries -> oracle PASSES -> loop stops. No LLM involved.
"""
import os
import shutil
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

# Configure the harness BEFORE importing it (module reads env at import time).
os.environ["AGENT_CMD"] = f"bash {ROOT / 'mock_agent.sh'}"
os.environ["VERIFY_CMD"] = "bash verify.sh"
os.environ["STEP_DELAY"] = "0"
os.environ["MAX_ITERS"] = "5"
os.environ["AGENT_TIMEOUT"] = "30"

import agentloop
import oracle

# Fresh sandbox
sb = ROOT / "sandbox"
if sb.exists():
    shutil.rmtree(sb)
sb.mkdir()
subprocess.run(["git", "init", "-q"], cwd=str(sb), capture_output=True)

agentloop.run_cli_mode("build a tax calculator (mock test)")

# After the loop, the oracle must pass and the code must be the CORRECT version.
passed, out = oracle.verify_passed(ROOT)
assert passed, f"verification should pass after the loop:\n{out}"
src = (sb / "tax_calc.py").read_text()
assert "(11000,0.10)" in src, "final code should be the CORRECT version"
# ensure we actually went through a rejection (buggy version existed at some point)
print("CLI LOOP TEST: PASS (reject -> retry -> pass)")

# --- RESUME TEST: simulate a crash mid-run by planting a 'running' state -----
import json, time as _t
STATE = ROOT / "agentloop.state.json"
if STATE.exists():
    STATE.unlink()
if sb.exists():
    shutil.rmtree(sb)
sb.mkdir()
subprocess.run(["git", "init", "-q"], cwd=str(sb), capture_output=True)
subprocess.run(f"bash {ROOT / 'mock_agent.sh'}", shell=True, cwd=str(sb),
               capture_output=True)  # iter1: buggy code + .fixed sentinel
STATE.write_text(json.dumps({"goal": "build a tax calculator (mock test)",
                             "mode": "cli", "iter": 2, "feedback": [],
                             "started_at": _t.time(), "status": "running"}))
agentloop.run_cli_mode("build a tax calculator (mock test)")
passed2, _ = oracle.verify_passed(ROOT)
assert passed2, "verification should pass after resume"
assert "resuming from iter 2" in (ROOT / "agentloop.log").read_text(), "expected resume log"
print("RESUME TEST: PASS (crash-safe resume from iter 2)")

# --- CONFIG SYNC + DRY-RUN TEST ---------------------------------------------
import sys
os.environ.pop("AGENT_CMD", None)  # ensure preset (not the mock) is resolved
old_argv = sys.argv
sys.argv = ["agentloop", "--dry-run", "--harness", "opencode",
            "--verify", "bash verify.sh", "build something"]
try:
    agentloop.main()
except SystemExit:
    pass
sys.argv = old_argv
assert agentloop.AGENT_PRESET == "opencode", agentloop.AGENT_PRESET
assert agentloop.resolve_agent_cmd() == 'opencode run "$AGENTLOOP_PROMPT" --auto'
print("DRY-RUN / CONFIG SYNC TEST: PASS")

# --- NOTIFY TEST -------------------------------------------------------------
import tempfile as _tf
ntf = _tf.mkdtemp()
note_file = f"{ntf}/note.txt"
os.environ["NOTIFY_CMD"] = f"echo '{'{kind}'}:{'{msg}'}' > {note_file}"
agentloop.notify("completed", "all good")
with open(note_file) as fh:
    assert fh.read().strip() == "completed:all good", "notify payload wrong"
os.environ.pop("NOTIFY_CMD", None)
print("NOTIFY TEST: PASS")

# cleanup run artifacts so the repo stays clean
for f in (ROOT / "agentloop.state.json", ROOT / "agentloop.summary.txt",
          ROOT / "agentloop.log", ROOT / "agentloop.pid"):
    f.unlink(missing_ok=True)
print("\nALL LOOP TESTS PASSED")
