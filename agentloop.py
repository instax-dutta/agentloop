#!/usr/bin/env python3
"""
agentloop.py — a harness-agnostic, self-verifying autonomy wrapper.

AgentLoop is NOT a coding agent and NOT a BYOK harness. It is a thin,
harness-agnostic wrapper that drives the coding agent you already use — OpenCode
by default (free models, no key from us), and also Kilo Code / Claude Code /
Aider / Codex — in a loop:

    goal + feedback  ->  your agent edits the sandbox  ->  verification oracle
         ^                                                     |
         |                      (fail) <-----------------------+
         +------------------------ (pass) -> DONE -------------+

The harness supplies the model and auth; AgentLoop only adds:
  * continuity (it loops until the goal is actually met),
  * the verification oracle (correctness gate — not "it runs"),
  * safety (never exposes your key to the wrapped agent; checkpoints via git).

Two modes:
  cli    (default) — shell out to an agent CLI (AGENT_CMD / AGENT_PRESET).
  direct (legacy)  — call an OpenAI-compatible API directly (no harness needed).
"""
import os
import sys
import json
import time
import subprocess
import signal
import pathlib
import datetime
import shutil

from oracle import (safe_env, run_verify, verify_passed, gate_done, ROOT)


def load_env():
    """Read .env (key=val) into the environment if not already set."""
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()  # must run before the config block below reads env vars

# ---- paths -----------------------------------------------------------------
SANDBOX = ROOT / "sandbox"
GOAL_FILE = ROOT / "goal.txt"
STOP_FILE = ROOT / "STOP"
PID_FILE = ROOT / "agentloop.pid"
LOG_FILE = ROOT / "agentloop.log"
STATE_FILE = ROOT / "agentloop.state.json"   # run state (for crash-safe resume)
SUMMARY_FILE = ROOT / "agentloop.summary.txt"

# ---- config (env-overridable) ----------------------------------------------
AGENT_MODE = os.environ.get("AGENT_MODE", "cli").lower()       # cli | direct
AGENT_PRESET = os.environ.get("AGENT_PRESET", "")              # opencode|kilocode|claude|aider|codex
AGENT_CMD = os.environ.get("AGENT_CMD", "")                   # explicit command (overrides preset)
MAX_ITERS = int(os.environ.get("MAX_ITERS", "50"))
WALL_CLOCK_SEC = int(os.environ.get("WALL_CLOCK_SEC", str(6 * 3600)))
STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "900"))

# direct-mode (legacy) config
API_KEY = os.environ.get("KILO_API_KEY") or os.environ.get("KILOCODE_API_KEY")
BASE_URL = os.environ.get("KILO_BASE_URL", "https://api.kilo.ai/api/gateway")
MODEL = os.environ.get("KILO_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
DIRECT_MAX_STEPS = int(os.environ.get("MAX_STEPS", "300"))
DIRECT_MSG_CAP = int(os.environ.get("MSG_CAP", "120"))

# ---- agent-CLI presets ------------------------------------------------------
# Each preset is a shell command; the prompt is injected via $AGENTLOOP_PROMPT
# (env var) so there are no quoting/curly-brace problems.
PRESETS = {
    "opencode": 'opencode run "$AGENTLOOP_PROMPT" --auto',
    "kilocode": 'kilocode run "$AGENTLOOP_PROMPT"',
    "claude":   'claude -p "$AGENTLOOP_PROMPT" --dangerously-skip-permissions',
    "aider":    'aider --message "$AGENTLOOP_PROMPT" --yes',
    "codex":    'codex exec "$AGENTLOOP_PROMPT"',
}


def resolve_agent_cmd():
    if AGENT_CMD:
        return AGENT_CMD
    preset = AGENT_PRESET or _auto_detect()
    if not preset:
        return ""
    return PRESETS.get(preset, preset)  # unknown preset -> treat as literal command


def _auto_detect():
    for name in ("opencode", "kilocode", "claude", "aider", "codex"):
        if shutil.which(name):
            return name
    return ""


# ---- logging ----------------------------------------------------------------
def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def git_checkpoint(sandbox: pathlib.Path, tag: str):
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(sandbox), capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", f"agentloop {tag}"],
                       cwd=str(sandbox), capture_output=True)
    except Exception:
        pass


def print_final(sandbox: pathlib.Path):
    files = sorted(str(p.relative_to(sandbox)) for p in sandbox.rglob("*")
                   if p.is_file() and ".git" not in p.parts)
    log("artifacts: " + ", ".join(files))


# ---- notifications ---------------------------------------------------------
def notify(kind: str, message: str):
    """Fire NOTIFY_CMD on a terminal state (e.g. DONE/BLOCKED/STOP).
    `{kind}` and `{msg}` in the command are substituted."""
    cmd = os.environ.get("NOTIFY_CMD", "")
    if not cmd:
        return
    try:
        rendered = cmd.replace("{kind}", kind).replace("{msg}", message)
        subprocess.run(rendered, shell=True, env=safe_env(),
                       capture_output=True, text=True, timeout=30)
    except Exception as e:
        log(f"notify failed: {e}")


# ---- runtime config (re-read so CLI args can override) ---------------------
def read_config():
    global AGENT_MODE, AGENT_PRESET, AGENT_CMD, MAX_ITERS, WALL_CLOCK_SEC, \
        STEP_DELAY, AGENT_TIMEOUT, DIRECT_MAX_STEPS, DIRECT_MSG_CAP
    AGENT_MODE = os.environ.get("AGENT_MODE", "cli").lower()
    AGENT_PRESET = os.environ.get("AGENT_PRESET", "")
    AGENT_CMD = os.environ.get("AGENT_CMD", "")
    MAX_ITERS = int(os.environ.get("MAX_ITERS", "50"))
    WALL_CLOCK_SEC = int(os.environ.get("WALL_CLOCK_SEC", str(6 * 3600)))
    STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
    AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "900"))
    DIRECT_MAX_STEPS = int(os.environ.get("MAX_STEPS", "300"))
    DIRECT_MSG_CAP = int(os.environ.get("MSG_CAP", "120"))


# ---- run state (crash-safe resume) -----------------------------------------
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def write_summary(status: str, iters: int, started_at: float, goal: str):
    elapsed = int(time.time() - started_at) if started_at else 0
    line = f"status={status} iters={iters} elapsed={elapsed}s goal={goal[:120]!r}"
    log("SUMMARY: " + line)
    try:
        SUMMARY_FILE.write_text(line + "\n")
    except Exception:
        pass
    notify(status, line)


def finish(status: str, iters: int, started_at: float, goal: str, it_next: int):
    """Mark a terminal run state, write the summary, and notify."""
    save_state({"goal": goal, "mode": AGENT_MODE, "iter": it_next,
                "feedback": [], "started_at": started_at, "status": status})
    write_summary(status, iters, started_at, goal)


# ============================================================================
# CLI MODE — drive an external coding-agent CLI in a verify/retry loop
# ============================================================================
def build_prompt(goal: str, feedback: list) -> str:
    p = (
        "You are a coding agent working AUTONOMOUSLY. There is NO human in the loop — "
        "never ask for clarification or confirmation; just act.\n"
        f"GOAL:\n{goal}\n\n"
        "Work ONLY inside the current working directory (the sandbox). Use your tools to "
        "implement and test the goal. Do NOT modify any verify/check script outside the sandbox.\n"
    )
    if feedback:
        p += ("YOUR PREVIOUS ATTEMPT FAILED VERIFICATION:\n"
              + feedback[-1][:2000]
              + "\n\nFix the code so it passes. Make the changes; keep explanations short.\n")
    else:
        p += ("Implement the goal now. When your work is complete and correct, stop. "
              "A verifier checks your output automatically, so aim for correctness, not just 'it runs'.\n")
    return p


def run_cli_mode(goal: str):
    cmd = resolve_agent_cmd()
    if not cmd:
        log("ERROR: no agent command resolved. Set AGENT_CMD or AGENT_PRESET, or install "
            "opencode/kilocode/claude/aider/codex.")
        sys.exit(2)
    log(f"CLI mode | agent_cmd={cmd}")
    SANDBOX.mkdir(parents=True, exist_ok=True)

    # --- crash-safe resume ---------------------------------------------------
    prev = load_state()
    resume = (prev.get("status") == "running" and prev.get("goal") == goal
              and isinstance(prev.get("iter"), int))
    if resume:
        it_start = prev["iter"]
        feedback = list(prev.get("feedback", []))
        started_at = prev.get("started_at", time.time())
        log(f"resuming from iter {it_start}")
    else:
        it_start = 1
        feedback = []
        started_at = time.time()
    save_state({"goal": goal, "mode": "cli", "iter": it_start,
                "feedback": feedback, "started_at": started_at, "status": "running"})

    start_wall = time.time()
    ran = 0
    status = "stopped"
    for it in range(it_start, MAX_ITERS + 1):
        ran += 1
        if STOP_FILE.exists():
            log("STOP file detected — halting.")
            finish("stopped", ran, started_at, goal, it + 1)
            return
        if time.time() - start_wall > WALL_CLOCK_SEC:
            log("wall-clock limit reached — halting.")
            finish("timeout", ran, started_at, goal, it + 1)
            return

        prompt = build_prompt(goal, feedback)
        env = safe_env()
        env["AGENTLOOP_PROMPT"] = prompt
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(SANDBOX), env=env,
                               capture_output=True, text=True, timeout=AGENT_TIMEOUT)
            rc_agent = r.returncode
            out = (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            rc_agent = None
            out = f"AGENT TIMEOUT after {AGENT_TIMEOUT}s"
            log(out)
        log(f"iter {it}: agent exit={rc_agent} -> {out[:200]!r}")

        git_checkpoint(SANDBOX, f"iter {it}")

        if os.environ.get("VERIFY_CMD"):
            passed, vout = verify_passed(ROOT)
            if passed:
                log(f"iter {it}: VERIFICATION PASSED ✓ — task complete.")
                print_final(SANDBOX)
                finish("completed", ran, started_at, goal, it + 1)
                return
            log(f"iter {it}: VERIFICATION FAILED — feeding results back to agent.")
            feedback.append(vout)
            feedback = feedback[-2:]
        else:
            # No oracle: rely on the agent signalling completion in its output.
            if "BLOCKED" in out:
                log("agent reported BLOCKED.")
                finish("blocked", ran, started_at, goal, it + 1)
                return
            if "DONE" in out:
                log("agent reported DONE (no verifier configured).")
                finish("completed", ran, started_at, goal, it + 1)
                return

        save_state({"goal": goal, "mode": "cli", "iter": it + 1,
                    "feedback": feedback, "started_at": started_at, "status": "running"})
        time.sleep(STEP_DELAY)

    # loop exhausted without completing
    finish("exhausted", ran, started_at, goal, MAX_ITERS + 1)


# ============================================================================
# DIRECT MODE (legacy) — call an OpenAI-compatible API directly, one thread
# ============================================================================
def run_direct_mode(goal: str):
    if not API_KEY:
        log("ERROR: direct mode needs KILO_API_KEY (or KILOCODE_API_KEY). "
            "Set it in .env, or use AGENT_MODE=cli with a real harness.")
        sys.exit(2)
    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=120, max_retries=1)

    # --- sandbox tools (only used in direct mode) ---
    DANGER = ["rm -rf /", "mkfs", "shutdown", "reboot", ":(){", "dd if=",
              "curl ", "wget ", "git push", "ssh ", "sudo ", "chmod -R 777",
              "/etc/", ".ssh", "kill -9", "crontab"]

    def confine(path: str) -> pathlib.Path:
        p = (SANDBOX / path).resolve()
        if p != SANDBOX and SANDBOX not in p.parents:
            raise ValueError(f"path escapes sandbox: {path}")
        return p

    def run_shell(cmd: str) -> str:
        if any(d in cmd for d in DANGER):
            return f"REFUSED (blocked pattern): {cmd}"
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(SANDBOX), env=safe_env(),
                               capture_output=True, text=True, timeout=120)
            return ((r.stdout or "") + (r.stderr or ""))[:6000] or "(no output)"
        except subprocess.TimeoutExpired:
            return "TIMEOUT after 120s"
        except Exception as e:
            return f"ERROR: {e}"

    def write_file(path: str, content: str) -> str:
        p = confine(path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
        return f"wrote {p.relative_to(SANDBOX)} ({len(content)} bytes)"

    def read_file(path: str) -> str:
        p = confine(path)
        return p.read_text()[:6000] if p.exists() else f"NOT FOUND: {path}"

    def list_dir(path: str = ".") -> str:
        p = confine(path)
        if not p.exists():
            return f"NOT FOUND: {path}"
        return "\n".join(sorted(str(x.relative_to(SANDBOX)) for x in p.iterdir())) or "(empty)"

    TOOLS = [{
        "type": "function", "function": {
            "name": "run_shell", "description": "Run a shell command INSIDE the sandbox only. No network/credential access.",
            "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}},
        {"type": "function", "function": {
            "name": "write_file", "description": "Write text to a path relative to the sandbox.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
        {"type": "function", "function": {
            "name": "read_file", "description": "Read a file relative to the sandbox.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {
            "name": "list_dir", "description": "List a sandbox directory (default: current).",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    ]
    DISPATCH = {"run_shell": run_shell, "write_file": write_file, "read_file": read_file, "list_dir": list_dir}

    SANDBOX.mkdir(parents=True, exist_ok=True)
    messages = [{
        "role": "system", "content": (
            "You are an autonomous coding agent running as ONE continuous session — a single "
            "unbroken reasoning thread. Your entire history is preserved.\nRULES:\n"
            "1. You will NEVER receive any user reply. NEVER ask for clarification.\n"
            "2. Always make progress by calling a tool. Do not just describe what you would do.\n"
            "3. Work ONLY inside the sandbox directory.\n"
            "4. When the goal is fully met AND verified by running/testing your work, reply with "
            "exactly: DONE. A verifier will be run against your work before DONE is accepted — your "
            "output must be CORRECT, not merely that it runs.\n"
            "5. Only if the goal is permanently impossible, reply exactly: BLOCKED\n")},
        {"role": "user", "content": f"GOAL:\n{goal}"}]

    start = time.time(); delay = STEP_DELAY; reflect_streak = 0
    status = "stopped"
    for step in range(1, DIRECT_MAX_STEPS + 1):
        if STOP_FILE.exists():
            log("STOP file detected — halting."); status = "stopped"; break
        if time.time() - start > WALL_CLOCK_SEC:
            log("wall-clock limit reached — halting."); status = "timeout"; break
        if len(messages) > DIRECT_MSG_CAP + 2:
            messages = [messages[0], messages[1]] + messages[-DIRECT_MSG_CAP:]
            log(f"compaction: history trimmed to {len(messages)} messages")
        try:
            r = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
            delay = STEP_DELAY
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                delay = min(delay * 2, 300); log(f"rate limited, backing off {int(delay)}s")
                time.sleep(delay); continue
            log(f"API error (will retry): {e}"); time.sleep(30); continue

        msg = r.choices[0].message
        messages.append(msg)
        text = (msg.content or "")
        if "DONE" in text:
            if gate_done(messages):
                status = "completed"; break
            time.sleep(delay); continue
        if "BLOCKED" in text:
            log("agent reported BLOCKED."); status = "blocked"; break
        if not msg.tool_calls:
            reflect_streak += 1
        if reflect_streak >= 3:
            log("agent reflected 3x in a row — assuming goal met, halting."); status = "exhausted"; break
            nudge = ("You must take a concrete action using a tool now. Do not ask questions. "
                     "If the goal is already met, reply exactly DONE."
                     if reflect_streak == 1 else
                     "FINAL: call a tool to make progress, or reply exactly DONE. No questions allowed.")
            messages.append({"role": "user", "content": nudge})
            log(f"step {step}: (reflection #{reflect_streak}) {text[:100]!r}")
            time.sleep(delay); continue
        reflect_streak = 0
        for tc in msg.tool_calls:
            fn = DISPATCH.get(tc.function.name)
            args = json.loads(tc.function.arguments or "{}")
            out = fn(**args) if fn else f"unknown tool {tc.function.name}"
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(out)})
            log(f"step {step}: {tc.function.name}({list(args.keys())}) -> {str(out)[:100]!r}")
        git_checkpoint(SANDBOX, f"step {step}")
        if os.environ.get("VERIFY_CMD") and int(os.environ.get("VERIFY_AT_STEP", "0")):
            _vs = int(os.environ.get("VERIFY_AT_STEP", "0"))
            if step % _vs == 0:
                rc, vout = run_verify(os.environ.get("VERIFY_CMD", ""), ROOT)
                if rc != 0:
                    log(f"step {step}: (verification failing) feeding results back")
                    messages.append({"role": "user", "content": "VERIFICATION CURRENTLY FAILS — fix before DONE:\n" + vout})
        time.sleep(delay)

    finish(status, step, start, goal, step + 1)


# ============================================================================
def _scaffold(args):
    """Create goal.txt / verify.sh / .env for a first run, then exit."""
    if args.goal:
        GOAL_FILE.write_text(args.goal + "\n")
    elif not GOAL_FILE.exists():
        GOAL_FILE.write_text("Describe the task the agent should complete and verify here.\n")
    if not (ROOT / "verify.sh").exists() and (ROOT / "verify_template.sh").exists():
        shutil.copy(ROOT / "verify_template.sh", ROOT / "verify.sh")
        os.chmod(ROOT / "verify.sh", 0o755)
    if not (ROOT / ".env").exists():
        preset = args.harness or "opencode"
        (ROOT / ".env").write_text(
            f"AGENT_MODE=cli\nAGENT_PRESET={preset}\nVERIFY_CMD=\"bash verify.sh\"\n")
    print("Scaffolded: goal.txt, verify.sh, .env")
    print("Edit verify.sh to assert correctness, then:  agentloop --dry-run")
    print("Launch:  ./launch.sh   |   or one-shot:  agentloop \"your goal\" --verify \"bash verify.sh\"")


def main():
    import argparse
    ap = argparse.ArgumentParser(
        prog="agentloop",
        description="Harness-agnostic, self-verifying autonomy wrapper for coding agents.")
    ap.add_argument("goal", nargs="?", help="task text (writes goal.txt; overrides the file)")
    ap.add_argument("--verify", help="set VERIFY_CMD — the verification oracle command")
    ap.add_argument("--harness", help="preset: opencode|kilocode|claude|aider|codex")
    ap.add_argument("--agent-cmd", help="explicit agent command (overrides --harness)")
    ap.add_argument("--mode", help="cli (default) | direct")
    ap.add_argument("--max-iters", type=int, help="max loop iterations")
    ap.add_argument("--wall", type=int, help="wall-clock limit in seconds")
    ap.add_argument("--step-delay", type=float, help="delay between iterations (s)")
    ap.add_argument("--init", action="store_true",
                    help="scaffold goal.txt + verify.sh + .env, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved configuration and exit (no loop)")
    args = ap.parse_args()

    if args.init:
        _scaffold(args)
        return

    # Apply CLI overrides into the environment, then re-read config globals.
    if args.verify:
        os.environ["VERIFY_CMD"] = args.verify
    if args.harness:
        os.environ["AGENT_PRESET"] = args.harness
    if args.agent_cmd:
        os.environ["AGENT_CMD"] = args.agent_cmd
    if args.mode:
        os.environ["AGENT_MODE"] = args.mode
    if args.max_iters is not None:
        os.environ["MAX_ITERS"] = str(args.max_iters)
    if args.wall is not None:
        os.environ["WALL_CLOCK_SEC"] = str(args.wall)
    if args.step_delay is not None:
        os.environ["STEP_DELAY"] = str(args.step_delay)
    read_config()

    goal = (args.goal if args.goal
            else (GOAL_FILE.read_text().strip() if GOAL_FILE.exists() else "No goal set."))

    if args.dry_run:
        cmd = resolve_agent_cmd()
        print("mode      :", AGENT_MODE)
        print("agent_cmd :", cmd or "(none resolved — set --harness/--agent-cmd)")
        print("verify    :", os.environ.get("VERIFY_CMD", "(none)"))
        print("goal      :", goal[:120])
        print("max_iters :", MAX_ITERS)
        print("wall_sec  :", WALL_CLOCK_SEC)
        return

    if args.goal:
        GOAL_FILE.write_text(args.goal + "\n")

    PID_FILE.write_text(str(os.getpid()))
    log(f"started | mode={AGENT_MODE} | sandbox={SANDBOX} | pid={os.getpid()}")
    if AGENT_MODE == "direct":
        run_direct_mode(goal)
    else:
        run_cli_mode(goal)
    PID_FILE.unlink(missing_ok=True)
    log("stopped.")


if __name__ == "__main__":
    main()
