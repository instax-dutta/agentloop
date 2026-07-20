#!/usr/bin/env python3
"""Deterministic test of the verification oracle (no LLM required)."""
import os
import subprocess
import pathlib

import oracle

ROOT = pathlib.Path(__file__).resolve().parent

# Ensure sandbox/tax_calc.py has the CORRECT version for verify.sh tests
# Run mock_agent.sh twice: first writes BUGGY, second writes CORRECT
_sb = ROOT / "sandbox"
_sb.mkdir(parents=True, exist_ok=True)
(_sb / ".fixed").unlink(missing_ok=True)  # Remove sentinel so first run writes BUGGY
subprocess.run(["bash", str(ROOT / "mock_agent.sh")], cwd=str(_sb), capture_output=True)
subprocess.run(["bash", str(ROOT / "mock_agent.sh")], cwd=str(_sb), capture_output=True)

# gate_done / run_verify read VERIFY_CMD from the environment at call time.
# 1) no verifier configured -> DONE is always accepted
os.environ["VERIFY_CMD"] = ""
assert oracle.gate_done([]) is True

# 2) passing verifier -> DONE accepted
os.environ["VERIFY_CMD"] = "true"
assert oracle.gate_done([]) is True

# 3) failing verifier -> DONE rejected AND feedback injected
os.environ["VERIFY_CMD"] = "false"
msgs = []
assert oracle.gate_done(msgs) is False
assert any(m["role"] == "user" and "VERIFICATION FAILED" in m["content"] for m in msgs), msgs
print("gate_done(): reject + inject  -> OK")

# 4) real oracle against the current (corrected) sandbox code must pass
os.environ["VERIFY_CMD"] = "bash verify.sh"
rc, out = oracle.run_verify("bash verify.sh", oracle.ROOT)
assert rc == 0, f"verify.sh failed unexpectedly:\n{out}"
print("run_verify(verify.sh): PASS")

# 5) real oracle must FAIL on intentionally broken code
import pathlib, shutil
sb = oracle.ROOT / "sandbox" / "tax_calc.py"
bak = oracle.ROOT / "sandbox" / "_tax_bak.py"
shutil.copy(sb, bak)
try:
    s = sb.read_text().replace("(11000, 0.10)", "(0, 0.10)")
    sb.write_text(s)
    rc2, _ = oracle.run_verify("bash verify.sh", oracle.ROOT)
    assert rc2 != 0, "oracle should have FAILED on broken code"
    print("run_verify(verify.sh) on broken code: FAIL (correct)")
finally:
    shutil.move(bak, sb)  # restore corrected code

# 6) sealed / held-out oracle: correct candidate passes, broken one fails
import tempfile, os as _os
tmp = pathlib.Path(tempfile.mkdtemp())
ref = tmp / "ref.py"
cand_ok = tmp / "ok.py"
cand_bad = tmp / "bad.py"
ref.write_text("import sys; print(int(sys.stdin.read().strip()) * 2)\n")
cand_ok.write_text("import sys; print(int(sys.stdin.read().strip()) * 2)\n")
cand_bad.write_text("import sys; print(int(sys.stdin.read().strip()) + 1)\n")
cases = tmp / "cases.txt"
cases.write_text("1\n2\n3\n4\n5\n")
oracle_file = tmp / "oracle.json"
SEAL = "test-secret"
data = oracle.record_reference(f"python3 {ref}", cases.read_text().splitlines(),
                               visible_n=2, out_path=oracle_file, seal_secret=SEAL)
assert data["visible"] == [0, 1] and len(data["heldout"]) == 3

g_ok = oracle.grade_candidate(f"python3 {cand_ok}", oracle_file, seal_secret=SEAL)
assert g_ok["passed"] and g_ok["heldout_pass"] == 3, g_ok
print("held-out grade (correct candidate): PASS")

g_bad = oracle.grade_candidate(f"python3 {cand_bad}", oracle_file, seal_secret=SEAL)
assert not g_bad["passed"] and g_bad["heldout_pass"] < 3, g_bad
print("held-out grade (broken candidate): FAIL (correct)")

# tamper detection: wrong seal -> tampered
g_tamper = oracle.grade_candidate(f"python3 {cand_ok}", oracle_file, seal_secret="wrong")
assert g_tamper["tampered"] and not g_tamper["passed"], g_tamper
print("held-out grade (wrong seal): TAMPERED (correct)")

# 7) safe_env: strip provider keys from agent; keep ORACLE_SEAL only for verify
os.environ["OPENAI_API_KEY"] = "sk-test-openai"
os.environ["ANTHROPIC_API_KEY"] = "sk-test-anthropic"
os.environ["KILO_API_KEY"] = "sk-test-kilo"
os.environ["ORACLE_SEAL"] = "held-out-secret"
os.environ["GITHUB_TOKEN"] = "ghp_test"
os.environ["MY_CUSTOM_VAR"] = "ok-to-pass"

agent_env = oracle.safe_env()
assert "OPENAI_API_KEY" not in agent_env, "OPENAI_API_KEY must not reach agent"
assert "ANTHROPIC_API_KEY" not in agent_env
assert "KILO_API_KEY" not in agent_env
assert "ORACLE_SEAL" not in agent_env, "ORACLE_SEAL must not reach agent"
assert "GITHUB_TOKEN" not in agent_env
assert agent_env.get("MY_CUSTOM_VAR") == "ok-to-pass"
assert "PATH" in agent_env

verify_env = oracle.safe_env(for_verify=True)
assert verify_env.get("ORACLE_SEAL") == "held-out-secret", "verifier needs ORACLE_SEAL"
assert "OPENAI_API_KEY" not in verify_env
assert "KILO_API_KEY" not in verify_env
print("safe_env agent vs verify scrubbing: PASS")

# 8) oracle.py gen: auto-generate inputs from a reference program
import tempfile, pathlib as _pl
_tmp = _pl.Path(tempfile.mkdtemp())
_gen_ref = _tmp / "gen_ref.py"
_gen_ref.write_text("import sys; print(int(sys.stdin.read().strip()) * 2)\n")
_gen_out = _tmp / "gen_cases.txt"
# Generate 20 inputs
inputs = oracle.gen_inputs(f"python3 {_gen_ref}", 20, _gen_out, seed=42)
assert 10 <= len(inputs) <= 20, f"expected 10-20 inputs, got {len(inputs)}"
assert _gen_out.exists(), "output file should exist"
lines = _gen_out.read_text().strip().splitlines()
assert 10 <= len(lines) <= 20, f"expected 10-20 lines, got {len(lines)}"
# Verify edge cases are included
all_text = "\n".join(lines)
assert "0" in all_text or any(l.strip() == "0" for l in lines), "edge case '0' should be included"
print(f"gen command: generated {len(lines)} inputs, edge cases present -> OK")

# Verify generated inputs actually work with the reference
import subprocess as _sp
for inp in lines[:5]:
    r = _sp.run(f"python3 {_gen_ref}", shell=True, input=inp, capture_output=True, text=True, timeout=5)
    assert r.returncode == 0, f"reference failed on input {inp!r}: {r.stderr}"
print("gen command: all tested inputs produce valid reference output -> OK")

# 9) gen + record + grade round-trip
_oracle_path = _tmp / "roundtrip_oracle.json"
data = oracle.record_reference(f"python3 {_gen_ref}", inputs, visible_n=5,
                                out_path=_oracle_path, seal_secret="test-seal")
assert data["visible"] == [0, 1, 2, 3, 4] and len(data["heldout"]) == len(inputs) - 5
print(f"gen+record round-trip: {len(data['visible'])} visible, {len(data['heldout'])} held-out -> OK")

# cleanup test secrets from this process
for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "KILO_API_KEY", "ORACLE_SEAL",
          "GITHUB_TOKEN", "MY_CUSTOM_VAR"):
    os.environ.pop(k, None)

print("\nALL ORACLE TESTS PASSED")
