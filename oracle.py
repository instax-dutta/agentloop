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
import random
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ORACLE_SEALED_DIR = ROOT / ".agentloop" / "oracle_sealed"

# Keys the agent (and untrusted subprocesses) must never inherit.
_EXPLICIT_SECRET_KEYS = frozenset({
    "KILO_API_KEY", "KILOCODE_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
    "XAI_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY", "PERPLEXITY_API_KEY",
    "HUGGINGFACE_TOKEN", "HF_TOKEN", "GITHUB_TOKEN", "GH_TOKEN",
    "ORACLE_SEAL",  # agent must never see the held-out seal
})

# Substrings that mark a key as credential-like (matched against key name, uppercased).
_SECRET_MARKERS = (
    "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "PRIVATE_KEY",
    "API_KEY", "AUTH_KEY", "ACCESS_KEY", "SESSION_KEY",
)

# Prefixes for cloud / infra credential namespaces.
_SECRET_PREFIXES = (
    "AWS_", "GCP_", "AZURE_", "GOOGLE_APPLICATION_", "KUBE", "SSH_",
)

# Always safe to pass through (needed for subprocesses to function).
_ALWAYS_PASS = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM",
    "TMPDIR", "TMP", "TEMP", "SHELL", "PWD", "OLDPWD", "SHLVL", "_",
    "SYSTEMROOT", "COMSPEC", "PATHEXT",  # Windows
})

# Env keys the verifier is allowed to receive even if they look sensitive.
_VERIFY_ALLOW = frozenset({"ORACLE_SEAL"})


def _is_secret_key(key: str) -> bool:
    u = key.upper()
    if u in _ALWAYS_PASS or u.startswith("LC_"):
        return False
    if u in _EXPLICIT_SECRET_KEYS:
        return True
    if any(m in u for m in _SECRET_MARKERS):
        return True
    if any(u.startswith(p) for p in _SECRET_PREFIXES):
        return True
    return False


def safe_env(*, for_verify: bool = False) -> dict:
    """Build a scrubbed environment for subprocesses.

    - Agent / notify / shell tools: credentials stripped, including ORACLE_SEAL.
    - Verifier (for_verify=True): same scrubbing, but ORACLE_SEAL is preserved
      so held-out grading via VERIFY_CMD can authenticate the seal.
    """
    allow = _VERIFY_ALLOW if for_verify else frozenset()
    e = {}
    for k, v in os.environ.items():
        if k.upper() in allow or k in allow:
            e[k] = v
            continue
        if not _is_secret_key(k):
            e[k] = v
    e["PATH"] = os.environ.get("PATH", "")
    # Belt-and-suspenders: never leave known provider keys in the child env.
    for k in _EXPLICIT_SECRET_KEYS:
        if k.upper() not in allow and k not in allow:
            e.pop(k, None)
    return e


def run_verify(cmd: str, cwd: pathlib.Path, timeout: int | None = None):
    """Run the ground-truth verification command. Returns (returncode, output)."""
    cmd = cmd or os.environ.get("VERIFY_CMD", "")
    if not cmd:
        return 0, ""
    if timeout is None:
        timeout = int(os.environ.get("VERIFY_TIMEOUT", "120"))
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(cwd), env=safe_env(for_verify=True),
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()[-2500:]
    except subprocess.TimeoutExpired:
        return 1, f"VERIFY TIMEOUT after {timeout}s"
    except Exception as e:
        return 1, f"VERIFY ERROR: {e}"


def verify_passed(cwd: pathlib.Path):
    """Convenience: returns (bool_passed, output) using VERIFY_CMD from env."""
    cmd = os.environ.get("VERIFY_CMD", "")
    if not cmd:
        return True, ""
    rc, out = run_verify(cmd, cwd)
    return rc == 0, out


def _oracle_log(msg: str):
    """Log without hard-importing agentloop at module load (avoids cycles)."""
    try:
        from agentloop import log as _log
        _log(msg)
    except Exception:
        print(msg, flush=True)


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
        _oracle_log("DONE rejected by verification (rc=%d)." % rc)
        messages.append({"role": "user", "content":
            "VERIFICATION FAILED — your work does not yet meet the goal:\n"
            + vout + "\nFix the code and continue. Only reply DONE once verification passes."})
        return False
    _oracle_log("DONE accepted — verification passed")
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


# ============================================================================
# INPUT GENERATOR — auto-produce fresh inputs from a reference program
# ============================================================================

def gen_inputs(reference_cmd: str, n: int, out_path: pathlib.Path,
               seed: int | None = None) -> list[str]:
    """Auto-generate `n` fresh input strings from a reference program.

    Strategies (applied in order until `n` inputs are accumulated):
    1. Random integers (positive, negative, zero, edge-case sizes like 0, 1, -1, MAXINT)
    2. Random floats (+ decimals, scientific notation)
    3. Random strings (alphanumeric, empty, whitespace, special chars)
    4. Structured data: JSON, CSV lines, key=value pairs
    5. If a previous input caused the reference to produce output, variant it

    Returns the list of generated input strings.
    """
    inputs: set[str] = set()
    rng = random.Random(seed if seed is not None else 42)
    generators = [
        _gen_integers,
        _gen_floats,
        _gen_strings,
        _gen_structured,
    ]

    # Edge cases always included
    edge_cases = ["0", "1", "-1", "", " ", "0.0", "null", "true", "false"]
    for ec in edge_cases:
        if len(inputs) >= n:
            break
        rc, _ = _try_reference(reference_cmd, ec)
        if rc == 0:  # program produced valid output
            inputs.add(ec)

    # Generative strategies
    while len(inputs) < n:
        for gen in generators:
            if len(inputs) >= n:
                break
            candidate = gen(rng)
            # Ensure uniqueness
            seen_key = candidate[:80]
            if seen_key in {i[:80] for i in inputs}:
                continue
            rc, _ = _try_reference(reference_cmd, candidate)
            if rc == 0:  # program produced valid output
                inputs.add(candidate)

    result = list(inputs)[:n]
    out_path = pathlib.Path(out_path)
    out_path.write_text("\n".join(result) + "\n")
    print(f"generated {len(result)} inputs -> {out_path}")
    return result


def _try_reference(cmd: str, inp: str) -> tuple[int | None, str]:
    """Run the reference command with input, return (returncode, output) or (None, error)."""
    try:
        r = subprocess.run(cmd, shell=True, input=inp, capture_output=True,
                           text=True, timeout=15)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception:
        return None, "error"


def _gen_integers(rng: random.Random) -> str:
    choice = rng.randint(0, 5)
    if choice == 0:
        return str(rng.randint(0, 1000))
    elif choice == 1:
        return str(rng.randint(-1000, 0))
    elif choice == 2:
        return str(rng.randint(10**6, 10**9))
    elif choice == 3:
        return f"{rng.randint(-10**9, -10**6)}"
    elif choice == 4:
        return str(rng.randint(0, 10))
    else:
        return str(rng.randint(-10, 10))


def _gen_floats(rng: random.Random) -> str:
    choice = rng.randint(0, 3)
    if choice == 0:
        return f"{rng.uniform(0, 1000):.2f}"
    elif choice == 1:
        return f"{rng.uniform(-1000, 1000):.4f}"
    elif choice == 2:
        return f"{rng.uniform(0, 1):.6f}"
    else:
        return f"{rng.gauss(500, 200):.2f}"


def _gen_strings(rng: random.Random) -> str:
    choice = rng.randint(0, 4)
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    if choice == 0:
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 20)))
    elif choice == 1:
        return " ".join("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 8))) for _ in range(rng.randint(1, 5)))
    elif choice == 2:
        return "single" if rng.random() < 0.5 else "married_joint"
    elif choice == 3:
        return "".join(rng.choice("!@#$%^&*()_+-={}[]|:;<>,.?/~`") for _ in range(rng.randint(1, 10)))
    else:
        return str(rng.randint(0, 10**6))


def _gen_structured(rng: random.Random) -> str:
    choice = rng.randint(0, 3)
    if choice == 0:
        # CSV-like
        return ",".join(str(rng.randint(0, 1000)) for _ in range(rng.randint(1, 5)))
    elif choice == 1:
        # JSON-like
        return json.dumps({f"k{rng.randint(1, 5)}": rng.randint(0, 100) for _ in range(rng.randint(1, 3))})
    elif choice == 2:
        # key=value pair
        return f"{rng.choice(['x','y','val','n','count'])}={rng.randint(0, 1000)}"
    else:
        # Two-number format (common for CLI tools)
        return f"{rng.randint(0, 500000)} {rng.choice(['single', 'married_joint'])}"


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

    gen = sub.add_parser("gen", help="auto-generate fresh inputs from a reference program")
    gen.add_argument("--reference", required=True, help="command; reads input on stdin, writes result to stdout")
    gen.add_argument("--n", type=int, default=50, help="number of inputs to generate")
    gen.add_argument("--out", required=True, help="output file path (one input per line)")
    gen.add_argument("--seed", type=int, default=None, help="random seed for reproducibility")

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
    if args.cmd == "gen":
        gen_inputs(args.reference, args.n, pathlib.Path(args.out), args.seed)
        return 0
    return 2


def _cli_entry():
    """Console-script entry point for setuptools."""
    raise SystemExit(_cli())


if __name__ == "__main__":
    _cli_entry()
