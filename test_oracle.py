#!/usr/bin/env python3
"""Deterministic test of the verification oracle (no LLM required)."""
import os
import oracle

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
    s = sb.read_text().replace("(11000,0.10)", "(0,0.10)")
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

print("\nALL ORACLE TESTS PASSED")
