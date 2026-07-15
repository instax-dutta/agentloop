#!/usr/bin/env python3
"""
oracle.py — the verification oracle for AgentLoop.

This is the correctness safety net that makes the autonomy loop trustworthy.
The agent's OWN tests are NOT trusted: an agent can validate "it runs and
prints" without noticing wrong numbers. Instead, a separate, human-authored
check (VERIFY_CMD, e.g. verify.sh) is run by the harness:

  - On a DONE/iteration, the harness runs VERIFY_CMD (cwd = project root).
  - Exit 0  -> accepted (task complete).
  - Non-zero -> rejected; the failure output is fed back so the agent must fix.

The agent never writes or edits the verifier, so it cannot fake the oracle.

SEALED / HELD-OUT ORACLE (the moat)
------------------------------------
A plain VERIFY_CMD can still be "overfit": if the author bakes the exact test
cases into the verifier, an agent can pass without being generally correct
(this is the SWE-bench false-green problem). To defeat that, AgentLoop ships a
held-out oracle:

  record  : capture a trusted REFERENCE's behaviour on a set of inputs, split
            into VISIBLE (may be shown to the agent) and HELD-OUT (the agent
            never sees these). A seal (hash) is stored so tampering is detectable.
  grade   : run a CANDIDATE on ALL inputs (visible + held-out) and report the
            held-out score. The candidate only passes if it is correct on the
            inputs it has never seen.

The held-out case file lives OUTSIDE the agent's sandbox (under
.agentloop/oracle_sealed/), so the agent cannot read or overfit to it.
"""
import os
import sys
import json
import hashlib
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ORACLE_SEALED_DIR = ROOT / ".agentloop" / "oracle_sealed"


def safe_env():
    """Strip credentials the agent must never read/exfiltrate; pass through PATH."""
    e = {k: v for k, v in os.environ.items()
         if not any(s in k.upper() for s in ("AWS", "GCP", "AZURE", "SSH",
                                             "TOKEN", "SECRET", "PASSWORD",
                                             "KUBE", "SEAL"))}
    e["PATH"] = os.environ.get("PATH", "")
    # safety valve so the wrapped *agent CLI* can never read our key either
    e.pop("KILO_API_KEY", None)
    e.pop("KILOCODE_API_KEY", None)
    return e


def run_verify(cmd: str, cwd: pathlib.Path):
    """Run the ground-truth verification command. Returns (returncode, output)."""
    cmd = cmd or os.environ.get("VERIFY_CMD", "")
    if not cmd:
        return 0, ""
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(cwd), env=safe_env(),
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()[-2500:]
    except subprocess.TimeoutExpired:
        return 1, "VERIFY TIMEOUT after 120s"
    except Exception as e:
        return 1, f"VERIFY ERROR: {e}"


def verify_passed(cwd: pathlib.Path):
    """Convenience: returns (bool_passed, output) using VERIFY_CMD from env."""
    cmd = os.environ.get("VERIFY_CMD", "")
    if not cmd:
        return True, ""
    rc, out = run_verify(cmd, cwd)
    return rc == 0, out


def gate_done(messages: list) -> bool:
    """Gate the DONE state (used by direct/OpenAI mode).

    Returns True if no verifier is configured, or the verifier passes.
    On failure, injects the verifier output as a user message and returns False
    so the agent is forced to keep working.
    """
    cmd = os.environ.get("VERIFY_CMD", "")
    if not cmd:
        return True
    rc, vout = run_verify(cmd, ROOT)
    if rc != 0:
        from agentloop import log
        log("DONE rejected by verification (rc=%d)." % rc)
        messages.append({"role": "user", "content":
            "VERIFICATION FAILED — your work does not yet meet the goal:\n"
            + vout + "\nFix the code and continue. Only reply DONE once verification passes."})
        return False
    from agentloop import log
    log("DONE accepted — verification passed ✓")
    return True


# ============================================================================
# SEALED / HELD-OUT ORACLE
# ============================================================================
def _run_program(cmd: str, inp: str, timeout: int = 30) -> str:
    """Run `cmd` with `inp` on stdin; return trimmed stdout (errors -> '')."""
    try:
        r = subprocess.run(cmd, shell=True, input=inp, capture_output=True,
                           text=True, timeout=timeout, env=safe_env())
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _seal(held_inputs, held_expected, secret: str) -> str:
    h = hashlib.sha256()
    for i, e in zip(held_inputs, held_expected):
        h.update((i + "\n" + e + "\n").encode())
    h.update((secret or "").encode())
    return h.hexdigest()


def record_reference(reference_cmd: str, inputs: list, visible_n: int,
                     out_path: pathlib.Path, seal_secret: str = "") -> dict:
    """Capture a trusted reference's behaviour into a sealed oracle file.

    `inputs`      : list of input strings (one per case).
    `visible_n`   : how many cases (from the front) are VISIBLE to the agent.
                    The rest are HELD-OUT (the agent never sees them).
    `out_path`    : where to write the oracle JSON (keep it OUTSIDE the sandbox).
    `seal_secret` : optional shared secret; if set, tampering with held-out
                    cases is detectable at grade time.
    Returns the oracle dict.
    """
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    expected = [_run_program(reference_cmd, i) for i in inputs]
    n = len(inputs)
    visible_n = max(0, min(visible_n, n))
    visible = list(range(visible_n))
    heldout = list(range(visible_n, n))
    held_inputs = [inputs[i] for i in heldout]
    held_expected = [expected[i] for i in heldout]
    data = {
        "version": 1,
        "reference_cmd": reference_cmd,
        "inputs": inputs,
        "expected": expected,
        "visible": visible,
        "heldout": heldout,
        "seal": _seal(held_inputs, held_expected, seal_secret),
    }
    out_path.write_text(json.dumps(data, indent=2))
    return data


def grade_candidate(candidate_cmd: str, oracle_path: pathlib.Path,
                    seal_secret: str = "", timeout: int = 30) -> dict:
    """Grade a CANDIDATE against a sealed oracle.

    Runs the candidate on EVERY input (visible + held-out), compares to the
    recorded expected output, and reports the held-out score. A candidate only
    PASSES if it is correct on the inputs it has never seen.

    Returns a dict with: passed, visible_pass, visible_total, heldout_pass,
    heldout_total, score, first_divergence, tampered.
    """
    oracle_path = pathlib.Path(oracle_path)
    data = json.loads(oracle_path.read_text())
    inputs = data["inputs"]
    expected = data["expected"]
    visible = data["visible"]
    heldout = data["heldout"]
    secret = seal_secret or os.environ.get("ORACLE_SEAL", "")

    # tamper check (only meaningful if a secret was used at record time)
    if data.get("seal") and secret:
        held_inputs = [inputs[i] for i in heldout]
        held_expected = [expected[i] for i in heldout]
        if _seal(held_inputs, held_expected, secret) != data["seal"]:
            return {"passed": False, "visible_pass": 0, "visible_total": len(visible),
                    "heldout_pass": 0, "heldout_total": len(heldout), "score": 0.0,
                    "first_divergence": None, "tampered": True}

    results = []
    for idx, inp in enumerate(inputs):
        got = _run_program(candidate_cmd, inp, timeout=timeout)
        results.append(got == expected[idx])

    def _count(idxs):
        return sum(1 for i in idxs if results[i]), len(idxs)

    v_pass, v_tot = _count(visible)
    h_pass, h_tot = _count(heldout)
    first_div = next((inputs[i] for i, ok in enumerate(results) if not ok), None)
    passed = (v_pass == v_tot) and (h_pass == h_tot) and (v_tot + h_tot > 0)
    score = (h_pass / h_tot) if h_tot else (1.0 if v_tot == 0 else v_pass / v_tot)
    return {"passed": passed, "visible_pass": v_pass, "visible_total": v_tot,
            "heldout_pass": h_pass, "heldout_total": h_tot, "score": score,
            "first_divergence": first_div, "tampered": False}


def _cli():
    import argparse
    ap = argparse.ArgumentParser(prog="oracle", description="AgentLoop held-out oracle")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="capture a reference's behaviour")
    r.add_argument("--reference", required=True, help="command; reads input on stdin, writes result to stdout")
    r.add_argument("--inputs", required=True, help="file with one input per line")
    r.add_argument("--visible", type=int, default=0, help="cases shown to the agent (rest are held-out)")
    r.add_argument("--out", required=True, help="output oracle JSON path (keep OUTSIDE the sandbox)")
    r.add_argument("--seal", default="", help="optional shared secret for tamper detection")

    g = sub.add_parser("grade", help="grade a candidate against a sealed oracle")
    g.add_argument("--candidate", required=True, help="command; reads input on stdin, writes result to stdout")
    g.add_argument("--oracle", required=True, help="oracle JSON from `record`")
    g.add_argument("--seal", default="", help="shared secret (must match `record`)")
    g.add_argument("--json", action="store_true", help="emit JSON instead of a human summary")

    args = ap.parse_args()
    if args.cmd == "record":
        inputs = [l for l in pathlib.Path(args.inputs).read_text().splitlines()]
        data = record_reference(args.reference, inputs, args.visible,
                                pathlib.Path(args.out), args.seal)
        print(f"recorded {len(data['inputs'])} cases "
              f"({len(data['visible'])} visible, {len(data['heldout'])} held-out) -> {args.out}")
        return 0
    if args.cmd == "grade":
        res = grade_candidate(args.candidate, pathlib.Path(args.oracle), args.seal)
        if args.json:
            print(json.dumps(res))
        else:
            tag = "TAMPERED" if res["tampered"] else ("PASS" if res["passed"] else "FAIL")
            print(f"[{tag}] visible {res['visible_pass']}/{res['visible_total']} "
                  f"held-out {res['heldout_pass']}/{res['heldout_total']} "
                  f"score={res['score']:.2f}")
            if res["first_divergence"] is not None:
                print(f"first divergence on input: {res['first_divergence']!r}")
        return 0 if res["passed"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
