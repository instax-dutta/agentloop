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
import argparse
import datetime
import json
import logging
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import RotatingFileHandler

from oracle import ROOT, gate_done, run_verify, safe_env, verify_passed

__version__ = "0.3.0"

# Process exit codes for scripting / CI
EXIT_COMPLETED = 0
EXIT_BLOCKED = 1
EXIT_CONFIG = 2
EXIT_TIMEOUT = 3
EXIT_EXHAUSTED = 4
EXIT_STOPPED = 130
EXIT_OVER_BUDGET = 5

_STATUS_EXIT = {
    "completed": EXIT_COMPLETED,
    "blocked": EXIT_BLOCKED,
    "timeout": EXIT_TIMEOUT,
    "exhausted": EXIT_EXHAUSTED,
    "stopped": EXIT_STOPPED,
    "over-budget": EXIT_OVER_BUDGET,
}


def load_env() -> None:
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
STATE_FILE = ROOT / "agentloop.state.json"
SUMMARY_FILE = ROOT / "agentloop.summary.txt"

# ---- config (env-overridable) ----------------------------------------------
AGENT_MODE = os.environ.get("AGENT_MODE", "cli").lower()
AGENT_PRESET = os.environ.get("AGENT_PRESET", "")
AGENT_CMD = os.environ.get("AGENT_CMD", "")
MAX_ITERS = int(os.environ.get("MAX_ITERS", "50"))
WALL_CLOCK_SEC = int(os.environ.get("WALL_CLOCK_SEC", str(6 * 3600)))
STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "900"))

# --- cost cap ---------------------------------------------------------------
MAX_COST_USD = float(os.environ.get("MAX_COST_USD", "0"))
ESTIMATED_COST_PER_ITER = float(os.environ.get("ESTIMATED_COST_PER_ITER", "0.10"))

# --- logging ----------------------------------------------------------------
LOG_MAX_MB = int(os.environ.get("LOG_MAX_MB", "10"))

# --- notifications ----------------------------------------------------------
NOTIFY_TELEGRAM_BOT_TOKEN = os.environ.get("NOTIFY_TELEGRAM_BOT_TOKEN", "")
NOTIFY_TELEGRAM_CHAT_ID = os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", "")
NOTIFY_DISCORD_WEBHOOK_URL = os.environ.get("NOTIFY_DISCORD_WEBHOOK_URL", "")
NOTIFY_SLACK_WEBHOOK_URL = os.environ.get("NOTIFY_SLACK_WEBHOOK_URL", "")

# direct-mode (legacy) config
API_KEY = os.environ.get("KILO_API_KEY") or os.environ.get("KILOCODE_API_KEY")
BASE_URL = os.environ.get("KILO_BASE_URL", "https://api.kilo.ai/api/gateway")
MODEL = os.environ.get("KILO_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
DIRECT_MAX_STEPS = int(os.environ.get("MAX_STEPS", "300"))
DIRECT_MSG_CAP = int(os.environ.get("MSG_CAP", "120"))

# ---- agent-CLI presets -----------------------------------------------------
# Each preset is a shell command; the prompt is injected via $AGENTLOOP_PROMPT
# (env var) so there are no quoting/curly-brace problems.
PRESETS = {
    "opencode": 'opencode run "$AGENTLOOP_PROMPT" --auto',
    "kilocode": 'kilocode run "$AGENTLOOP_PROMPT"',
    "claude":   'claude -p "$AGENTLOOP_PROMPT" --dangerously-skip-permissions',
    "aider":    'aider --message "$AGENTLOOP_PROMPT" --yes',
    "codex":    'codex exec "$AGENTLOOP_PROMPT"',
    "goose":    'goose run "$AGENTLOOP_PROMPT"',
}

# Last terminal status (for process exit code)
_last_status: dict[str, str] = {"status": "stopped"}


def resolve_agent_cmd() -> str:
    if AGENT_CMD:
        return AGENT_CMD
    preset = AGENT_PRESET or _auto_detect()
    if not preset:
        return ""
    return PRESETS.get(preset, preset)


def _auto_detect() -> str:
    """Detect an installed agent CLI, version-checking each candidate."""
    candidates = ["opencode", "kilocode", "claude", "aider", "codex", "goose"]
    for name in candidates:
        binary = shutil.which(name)
        if binary:
            # Quick version / availability check
            try:
                r = subprocess.run(
                    [name, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 or r.returncode is None:
                    return name
                # Some CLIs return non-zero for --version; still accept them
                if "version" in (r.stdout + r.stderr).lower():
                    return name
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
            # Binary exists but didn't respond to --version — still usable
            return name
    return ""


# ---- logging ----------------------------------------------------------------
_logger_initialized = False


def _init_logger() -> None:
    """Set up rotating file logger + console output."""
    global _logger_initialized
    logger = logging.getLogger("agentloop")
    logger.setLevel(logging.DEBUG)

    # Rotating file handler
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            str(LOG_FILE), maxBytes=LOG_MAX_MB * 1024 * 1024, backupCount=3,
        )
        fh.setFormatter(logging.Formatter(
            "[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    except Exception:
        pass

    _logger_initialized = True


def log(msg: str) -> None:
    """Log a timestamped line to both the rotating log file and stdout."""
    global _logger_initialized
    if not _logger_initialized:
        _init_logger()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        logging.getLogger("agentloop").info(msg)
    except Exception:
        pass


# ---- atomic I/O ------------------------------------------------------------
def atomic_write(path: pathlib.Path, text: str) -> None:
    """Write via temp file + rename so a crash cannot leave a torn file."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        pathlib.Path(tmp_name).replace(path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---- sandbox git -----------------------------------------------------------
def ensure_sandbox_git(sandbox: pathlib.Path) -> bool:
    """Make sure the sandbox is a git repo so checkpoints can land. Returns ok."""
    sandbox.mkdir(parents=True, exist_ok=True)
    git_dir = sandbox / ".git"
    if git_dir.exists():
        return True
    try:
        r = subprocess.run(["git", "init", "-q"], cwd=str(sandbox),
                           capture_output=True, text=True)
        if r.returncode != 0:
            log(f"git init failed in sandbox: {(r.stderr or r.stdout or '').strip()}")
            return False
        subprocess.run(["git", "config", "user.email", "agentloop@local"],
                       cwd=str(sandbox), capture_output=True)
        subprocess.run(["git", "config", "user.name", "agentloop"],
                       cwd=str(sandbox), capture_output=True)
        return True
    except Exception as e:
        log(f"git init error: {e}")
        return False


def git_checkpoint(sandbox: pathlib.Path, tag: str) -> None:
    if not ensure_sandbox_git(sandbox):
        return
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(sandbox), capture_output=True)
        r = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", f"agentloop {tag}"],
                           cwd=str(sandbox), capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            if err and "nothing to commit" not in err.lower():
                log(f"git checkpoint failed ({tag}): {err[:200]}")
    except Exception as e:
        log(f"git checkpoint error ({tag}): {e}")


def print_final(sandbox: pathlib.Path) -> None:
    files = sorted(str(p.relative_to(sandbox)) for p in sandbox.rglob("*")
                   if p.is_file() and ".git" not in p.parts)
    log("artifacts: " + ", ".join(files))


def terminal_token(text: str, token: str) -> bool:
    """True if any full line of text is exactly `token` (avoids substring false positives)."""
    if not text:
        return False
    return any(line.strip() == token for line in text.splitlines())


# ---- notifications ---------------------------------------------------------
def notify(kind: str, message: str) -> None:
    """Fire NOTIFY_CMD on a terminal state (e.g. DONE/BLOCKED/STOP).
    `{kind}` and `{msg}` in the command are substituted."""
    cmd = os.environ.get("NOTIFY_CMD", "")
    if cmd:
        try:
            safe_msg = message.replace("'", "").replace('"', "")[:500]
            rendered = cmd.replace("{kind}", kind).replace("{msg}", safe_msg)
            subprocess.run(rendered, shell=True, env=safe_env(),
                           capture_output=True, text=True, timeout=30)
        except Exception as e:
            log(f"notify cmd failed: {e}")

    # Native adapters
    if kind in ("completed", "blocked", "stopped", "timeout", "over-budget"):
        _notify_telegram(kind, message)
        _notify_discord(kind, message)
        _notify_slack(kind, message)


def _notify_telegram(kind: str, message: str) -> None:
    """Send notification via Telegram Bot API."""
    token = NOTIFY_TELEGRAM_BOT_TOKEN
    chat_id = NOTIFY_TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        safe_msg = message[:2000].replace("'", "").replace('"', "")
        text = f"[AgentLoop] {kind.upper()}\n{safe_msg}"
        data = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"telegram notify failed: {e}")


def _notify_discord(kind: str, message: str) -> None:
    """Send notification via Discord webhook."""
    url = NOTIFY_DISCORD_WEBHOOK_URL
    if not url:
        return
    try:
        safe_msg = message[:2000].replace("'", "").replace('"', "")
        data = json.dumps({
            "content": f"**[AgentLoop] {kind.upper()}**\n{safe_msg}",
        }).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"discord notify failed: {e}")


def _notify_slack(kind: str, message: str) -> None:
    """Send notification via Slack webhook."""
    url = NOTIFY_SLACK_WEBHOOK_URL
    if not url:
        return
    try:
        safe_msg = message[:2000].replace("'", "").replace('"', "")
        data = json.dumps({
            "text": f"[AgentLoop] *{kind.upper()}*\n{safe_msg}",
        }).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"slack notify failed: {e}")


# ---- runtime config --------------------------------------------------------
def read_config() -> None:
    """(Re)-read config from environment (called after CLI overrides)."""
    global AGENT_MODE, AGENT_PRESET, AGENT_CMD, MAX_ITERS, WALL_CLOCK_SEC, \
        STEP_DELAY, AGENT_TIMEOUT, DIRECT_MAX_STEPS, DIRECT_MSG_CAP, API_KEY, \
        BASE_URL, MODEL, MAX_COST_USD, ESTIMATED_COST_PER_ITER, LOG_MAX_MB, \
        NOTIFY_TELEGRAM_BOT_TOKEN, NOTIFY_TELEGRAM_CHAT_ID, \
        NOTIFY_DISCORD_WEBHOOK_URL, NOTIFY_SLACK_WEBHOOK_URL
    AGENT_MODE = os.environ.get("AGENT_MODE", "cli").lower()
    AGENT_PRESET = os.environ.get("AGENT_PRESET", "")
    AGENT_CMD = os.environ.get("AGENT_CMD", "")
    MAX_ITERS = int(os.environ.get("MAX_ITERS", "50"))
    WALL_CLOCK_SEC = int(os.environ.get("WALL_CLOCK_SEC", str(6 * 3600)))
    STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
    AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "900"))
    MAX_COST_USD = float(os.environ.get("MAX_COST_USD", "0"))
    ESTIMATED_COST_PER_ITER = float(os.environ.get("ESTIMATED_COST_PER_ITER", "0.10"))
    LOG_MAX_MB = int(os.environ.get("LOG_MAX_MB", "10"))
    NOTIFY_TELEGRAM_BOT_TOKEN = os.environ.get("NOTIFY_TELEGRAM_BOT_TOKEN", "")
    NOTIFY_TELEGRAM_CHAT_ID = os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", "")
    NOTIFY_DISCORD_WEBHOOK_URL = os.environ.get("NOTIFY_DISCORD_WEBHOOK_URL", "")
    NOTIFY_SLACK_WEBHOOK_URL = os.environ.get("NOTIFY_SLACK_WEBHOOK_URL", "")
    DIRECT_MAX_STEPS = int(os.environ.get("MAX_STEPS", "300"))
    DIRECT_MSG_CAP = int(os.environ.get("MSG_CAP", "120"))
    API_KEY = os.environ.get("KILO_API_KEY") or os.environ.get("KILOCODE_API_KEY")
    BASE_URL = os.environ.get("KILO_BASE_URL", "https://api.kilo.ai/api/gateway")
    MODEL = os.environ.get("KILO_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")


# ---- run state (crash-safe resume) -----------------------------------------
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        atomic_write(STATE_FILE, json.dumps(state, indent=2) + "\n")
    except Exception as e:
        log(f"save_state failed: {e}")


def write_summary(status: str, iters: int, started_at: float, goal: str, running_cost: float = 0) -> None:
    elapsed = int(time.time() - started_at) if started_at else 0
    cost_str = f"cost=${running_cost:.2f}" if running_cost > 0 else ""
    line = f"status={status} iters={iters} elapsed={elapsed}s goal={goal[:120]!r} {cost_str}".strip()
    log("SUMMARY: " + line)
    try:
        atomic_write(SUMMARY_FILE, line + "\n")
    except Exception as e:
        log(f"write_summary failed: {e}")
    notify(status, line)


def finish(status: str, iters: int, started_at: float, goal: str, it_next: int, running_cost: float = 0) -> None:
    """Mark a terminal run state, write the summary, and notify."""
    _last_status["status"] = status
    save_state({
        "goal": goal, "mode": AGENT_MODE, "iter": it_next,
        "feedback": [], "started_at": started_at, "status": status,
        "running_cost": running_cost,
    })
    write_summary(status, iters, started_at, goal, running_cost)


def _install_signal_handlers() -> None:
    """On SIGTERM/SIGINT, create STOP so the loop exits cleanly with a summary."""
    def _handler(signum, _frame) -> None:
        try:
            STOP_FILE.write_text("")
        except Exception:
            pass
        log(f"signal {signum} received — STOP set; will halt after current step")

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


# ---- input validation ------------------------------------------------------
def _validate_goal(goal: str) -> str:
    """Validate and sanitize the goal string."""
    if not goal or not goal.strip():
        log("ERROR: goal is empty. Set a goal in goal.txt or pass it as an argument.")
        sys.exit(EXIT_CONFIG)
    goal = goal.strip()
    if len(goal) > 10000:
        log("WARNING: goal exceeds 10000 characters, truncating.")
        goal = goal[:10000]
    # Warn about potentially dangerous content
    dangerous = ["rm -rf", "sudo ", "chmod 777", "> /dev/sda"]
    for d in dangerous:
        if d in goal.lower():
            log(f"WARNING: goal contains potentially dangerous pattern: {d!r}")
    return goal


def _validate_config() -> None:
    """Validate runtime configuration values."""
    if MAX_ITERS < 1:
        log("ERROR: MAX_ITERS must be >= 1")
        sys.exit(EXIT_CONFIG)
    if WALL_CLOCK_SEC < 1:
        log("ERROR: WALL_CLOCK_SEC must be >= 1")
        sys.exit(EXIT_CONFIG)
    if STEP_DELAY < 0:
        log("ERROR: STEP_DELAY must be >= 0")
        sys.exit(EXIT_CONFIG)
    if AGENT_TIMEOUT < 1:
        log("ERROR: AGENT_TIMEOUT must be >= 1")
        sys.exit(EXIT_CONFIG)
    if MAX_COST_USD < 0:
        log("ERROR: MAX_COST_USD must be >= 0")
        sys.exit(EXIT_CONFIG)
    if LOG_MAX_MB < 1:
        log("ERROR: LOG_MAX_MB must be >= 1")
        sys.exit(EXIT_CONFIG)


# ============================================================================
# CLI MODE — drive an external coding-agent CLI in a verify/retry loop
# ============================================================================
def build_prompt(goal: str, feedback: list, cost_info: str = "") -> str:
    p = (
        "You are a coding agent working AUTONOMOUSLY. There is NO human in the loop — "
        "never ask for clarification or confirmation; just act.\n"
        f"GOAL:\n{goal}\n\n"
        "Work ONLY inside the current working directory (the sandbox). Use your tools to "
        "implement and test the goal. Do NOT modify any verify/check script outside the sandbox.\n"
    )
    if cost_info:
        p += f"Note: {cost_info}\n"
    if feedback:
        p += ("YOUR PREVIOUS ATTEMPT FAILED VERIFICATION:\n"
              + feedback[-1][:2000]
              + "\n\nFix the code so it passes. Make the changes; keep explanations short.\n")
    else:
        p += ("Implement the goal now. When your work is complete and correct, stop. "
              "A verifier checks your output automatically, so aim for correctness, not just 'it runs'.\n")
    return p


def run_cli_mode(goal: str) -> str:
    cmd = resolve_agent_cmd()
    if not cmd:
        log("ERROR: no agent command resolved. Set AGENT_CMD or AGENT_PRESET, or install "
            "opencode/kilocode/claude/aider/codex.")
        sys.exit(EXIT_CONFIG)
    log(f"CLI mode | agent_cmd={cmd}")
    ensure_sandbox_git(SANDBOX)

    prev = load_state()
    resume = (prev.get("status") == "running" and prev.get("goal") == goal
              and isinstance(prev.get("iter"), int))
    if resume:
        it_start = prev["iter"]
        feedback = list(prev.get("feedback", []))
        started_at = prev.get("started_at", time.time())
        running_cost = prev.get("running_cost", 0.0)
        log(f"resuming from iter {it_start} (cost so far: ${running_cost:.2f})")
    else:
        it_start = 1
        feedback = []
        started_at = time.time()
        running_cost = 0.0

    save_state({
        "goal": goal, "mode": "cli", "iter": it_start,
        "feedback": feedback, "started_at": started_at, "status": "running",
        "running_cost": running_cost,
    })

    ran = 0
    for it in range(it_start, MAX_ITERS + 1):
        ran += 1

        # --- STOP file check ---
        if STOP_FILE.exists():
            log("STOP file detected — halting.")
            finish("stopped", ran, started_at, goal, it + 1, running_cost)
            return "stopped"

        # --- Wall-clock check (absolute from run start, survives resume) ---
        if time.time() - started_at > WALL_CLOCK_SEC:
            log("wall-clock limit reached — halting.")
            finish("timeout", ran, started_at, goal, it + 1, running_cost)
            return "timeout"

        # --- Cost cap check ---
        if MAX_COST_USD > 0 and running_cost > MAX_COST_USD:
            log(f"cost cap exceeded (${running_cost:.2f} > ${MAX_COST_USD:.2f}) — halting.")
            finish("over-budget", ran, started_at, goal, it + 1, running_cost)
            return "over-budget"

        cost_info = ""
        if MAX_COST_USD > 0:
            remaining = MAX_COST_USD - running_cost
            cost_info = f"running cost ${running_cost:.2f}, remaining budget ${remaining:.2f}"

        prompt = build_prompt(goal, feedback, cost_info)
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

        # Estimate cost (rough: each iteration = 1 agent invocation)
        if MAX_COST_USD > 0:
            running_cost += ESTIMATED_COST_PER_ITER

        git_checkpoint(SANDBOX, f"iter {it}")

        if os.environ.get("VERIFY_CMD"):
            passed, vout = verify_passed(ROOT)
            if passed:
                log(f"iter {it}: VERIFICATION PASSED — task complete.")
                print_final(SANDBOX)
                finish("completed", ran, started_at, goal, it + 1, running_cost)
                return "completed"
            log(f"iter {it}: VERIFICATION FAILED — feeding results back to agent.")
            feedback.append(vout)
            feedback = feedback[-2:]
        else:
            if terminal_token(out, "BLOCKED"):
                log("agent reported BLOCKED.")
                finish("blocked", ran, started_at, goal, it + 1, running_cost)
                return "blocked"
            if terminal_token(out, "DONE"):
                log("agent reported DONE (no verifier configured).")
                finish("completed", ran, started_at, goal, it + 1, running_cost)
                return "completed"

        save_state({
            "goal": goal, "mode": "cli", "iter": it + 1,
            "feedback": feedback, "started_at": started_at, "status": "running",
            "running_cost": running_cost,
        })
        time.sleep(STEP_DELAY)

    finish("exhausted", ran, started_at, goal, MAX_ITERS + 1, running_cost)
    return "exhausted"


# ============================================================================
# DIRECT MODE (legacy) — call an OpenAI-compatible API directly, one thread
# ============================================================================
def run_direct_mode(goal: str) -> str:
    if not API_KEY:
        log("ERROR: direct mode needs KILO_API_KEY (or KILOCODE_API_KEY). "
            "Set it in .env, or use AGENT_MODE=cli with a real harness.")
        sys.exit(EXIT_CONFIG)
    try:
        from openai import OpenAI
    except ImportError:
        log("ERROR: direct mode requires the openai package. "
            "Install with:  pip install 'agentloop[direct]'  or  pip install openai")
        sys.exit(EXIT_CONFIG)
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=120, max_retries=1)

    danger = ["rm -rf /", "mkfs", "shutdown", "reboot", ":(){" , "dd if=",
               "curl ", "wget ", "git push", "ssh ", "sudo ", "chmod -R 777",
               "/etc/", ".ssh", "kill -9", "crontab"]

    def confine(path: str) -> pathlib.Path:
        p = (SANDBOX / path).resolve()
        if p != SANDBOX and SANDBOX not in p.parents:
            raise ValueError(f"path escapes sandbox: {path}")
        return p

    def run_shell(cmd: str) -> str:
        if any(d in cmd for d in danger):
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
        p = confine(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {p.relative_to(SANDBOX)} ({len(content)} bytes)"

    def read_file(path: str) -> str:
        p = confine(path)
        return p.read_text()[:6000] if p.exists() else f"NOT FOUND: {path}"

    def list_dir(path: str = ".") -> str:
        p = confine(path)
        if not p.exists():
            return f"NOT FOUND: {path}"
        return "\n".join(sorted(str(x.relative_to(SANDBOX)) for x in p.iterdir())) or "(empty)"

    tools = [
        {"type": "function", "function": {
            "name": "run_shell", "description": "Run a shell command INSIDE the sandbox.",
            "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}},
        {"type": "function", "function": {
            "name": "write_file", "description": "Write text to a path relative to the sandbox.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read a file relative to the sandbox.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {
            "name": "list_dir",
            "description": "List a sandbox directory (default: current).",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    ]
    dispatch = {"run_shell": run_shell, "write_file": write_file,
                 "read_file": read_file, "list_dir": list_dir}

    ensure_sandbox_git(SANDBOX)
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

    start = time.time()
    delay = STEP_DELAY
    reflect_streak = 0
    status = "stopped"
    step = 0
    running_cost = 0.0

    for step in range(1, DIRECT_MAX_STEPS + 1):
        if STOP_FILE.exists():
            log("STOP file detected — halting.")
            status = "stopped"
            break
        if time.time() - start > WALL_CLOCK_SEC:
            log("wall-clock limit reached — halting.")
            status = "timeout"
            break
        if MAX_COST_USD > 0 and running_cost > MAX_COST_USD:
            log(f"cost cap exceeded (${running_cost:.2f} > ${MAX_COST_USD:.2f}) — halting.")
            status = "over-budget"
            break

        if len(messages) > DIRECT_MSG_CAP + 2:
            messages = [messages[0], messages[1]] + messages[-DIRECT_MSG_CAP:]
            log(f"compaction: history trimmed to {len(messages)} messages")

        try:
            r = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
            delay = STEP_DELAY
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                delay = min(delay * 2, 300)
                log(f"rate limited, backing off {int(delay)}s")
                time.sleep(delay)
                continue
            log(f"API error (will retry): {e}")
            time.sleep(30)
            continue

        # Estimate cost (rough: count input + output tokens if available)
        if hasattr(r, "usage") and r.usage:
            input_tokens = getattr(r.usage, "prompt_tokens", 0)
            output_tokens = getattr(r.usage, "completion_tokens", 0)
            # Rough pricing for common models: ~$3/M input, ~$15/M output
            step_cost = (input_tokens * 0.000003 + output_tokens * 0.000015)
            running_cost += step_cost
        elif MAX_COST_USD > 0:
            running_cost += ESTIMATED_COST_PER_ITER / 10  # finer granularity

        msg = r.choices[0].message
        messages.append(msg)
        text = (msg.content or "")
        if terminal_token(text, "DONE") or text.strip() == "DONE":
            if gate_done(messages):
                status = "completed"
                break
            time.sleep(delay)
            continue
        if terminal_token(text, "BLOCKED") or text.strip() == "BLOCKED":
            log("agent reported BLOCKED.")
            status = "blocked"
            break

        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            reflect_streak += 1
            if reflect_streak >= 3:
                log("agent reflected 3x in a row without tools — assuming stuck, halting.")
                status = "exhausted"
                break
            if reflect_streak == 1:
                nudge = ("You must take a concrete action using a tool now. Do not ask questions. "
                         "If the goal is already met, reply exactly DONE.")
            else:
                nudge = ("FINAL: call a tool to make progress, or reply exactly DONE. "
                         "No questions allowed.")
            messages.append({"role": "user", "content": nudge})
            log(f"step {step}: (reflection #{reflect_streak}) {text[:100]!r}")
            time.sleep(delay)
            continue

        reflect_streak = 0
        for tc in tool_calls:
            fn = dispatch.get(tc.function.name)
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
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
                    messages.append({"role": "user", "content":
                        "VERIFICATION CURRENTLY FAILS — fix before DONE:\n" + vout})
        time.sleep(delay)

    finish(status, step, start, goal, step + 1, running_cost)
    return status


# ============================================================================
# STATUS / MONITORING
# ============================================================================
def cmd_status(args: argparse.Namespace) -> int:
    """Print the status of the latest (or current) run."""
    state = load_state()
    summary_text = ""
    try:
        summary_text = SUMMARY_FILE.read_text().strip()
    except Exception:
        pass

    if not state and not summary_text:
        print("No runs found.")
        return EXIT_COMPLETED

    print("=" * 60)
    print("  AgentLoop Run Status")
    print("=" * 60)

    if state:
        status = state.get("status", "unknown")
        iters = state.get("iter", 0)
        goal = state.get("goal", "")[:80]
        started_at = state.get("started_at", 0)
        mode = state.get("mode", "cli")
        running_cost = state.get("running_cost", 0.0)

        elapsed = int(time.time() - started_at) if started_at else 0
        status_display = status
        if status == "running":
            status_display = "🟢 RUNNING"
        elif status == "completed":
            status_display = "✅ COMPLETED"
        elif status == "blocked":
            status_display = "🔴 BLOCKED"
        elif status == "timeout":
            status_display = "⏰ TIMEOUT"
        elif status == "exhausted":
            status_display = "⚠️ EXHAUSTED"
        elif status == "stopped":
            status_display = "🛑 STOPPED"
        elif status == "over-budget":
            status_display = "💰 OVER-BUDGET"

        print(f"  Status     : {status_display}")
        print(f"  Goal       : {goal}")
        print(f"  Mode       : {mode}")
        print(f"  Iterations : {iters}")
        print(f"  Elapsed    : {elapsed}s")
        if running_cost > 0:
            print(f"  Cost       : ${running_cost:.2f}")
        if status == "running":
            pid_path = PID_FILE
            if pid_path.exists():
                try:
                    pid = int(pid_path.read_text().strip())
                    print(f"  PID        : {pid}")
                except Exception:
                    pass

    if summary_text:
        print(f"  Summary    : {summary_text}")

    print("=" * 60)

    # Check if PID is active
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            try:
                os.kill(pid, 0)
                print(f"  (Process {pid} is alive)")
            except OSError:
                print(f"  (Process {pid} is dead — stale PID file)")
    except Exception:
        pass

    return EXIT_COMPLETED


def cmd_serve(args: argparse.Namespace) -> int:
    """Start a tiny web server showing run status."""
    port = args.port if args.port else 8080
    html_page = textwrap.dedent("""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>AgentLoop Monitor</title>
    <style>
      * { margin:0; padding:0; box-sizing:border-box; }
      body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
             background:#0d1117; color:#c9d1d9; padding:2rem; }
      h1 { color:#58a6ff; margin-bottom:0.5rem; }
      .card { background:#161b22; border:1px solid #30363d; border-radius:8px;
              padding:1.5rem; margin:1rem 0; }
      .card h2 { color:#f0f6fc; font-size:1.1rem; margin-bottom:0.8rem; }
      .row { display:flex; justify-content:space-between; padding:0.3rem 0;
             border-bottom:1px solid #21262d; }
      .row:last-child { border-bottom:none; }
      .label { color:#8b949e; }
      .value { color:#f0f6fc; }
      .status-badge { display:inline-block; padding:0.2rem 0.6rem; border-radius:12px;
                       font-size:0.85rem; font-weight:600; }
      .running { background:#1b4123; color:#3fb950; }
      .completed { background:#1b4123; color:#3fb950; }
      .blocked { background:#561c1c; color:#f85149; }
      .timeout { background:#3d2e00; color:#d29922; }
      .stopped { background:#21262d; color:#8b949e; }
      .footer { text-align:center; color:#484f58; margin-top:2rem; font-size:0.85rem; }
      pre { background:#0d1117; padding:0.8rem; border-radius:6px; overflow-x:auto;
            font-size:0.85rem; margin-top:0.5rem; }
    </style>
    <script>
      setInterval(() => location.reload(), 5000);
    </script>
    </head>
    <body>
    <h1>🔁 AgentLoop Monitor</h1>
    <p id="ts" style="color:#8b949e;margin-bottom:1rem;">refreshing every 5s</p>
    <script>
      const now = new Date();
      document.getElementById('ts').textContent =
        'Last updated: ' + now.toLocaleTimeString() + ' (auto-refresh 5s)';
    </script>
    """)

    def _render_status() -> str:
        state = load_state()
        summary_text = ""
        try:
            summary_text = SUMMARY_FILE.read_text().strip()
        except Exception:
            pass

        if not state:
            return html_page + "<div class='card'><h2>No runs found</h2></div>"

        status = state.get("status", "unknown")
        goal = state.get("goal", "")[:100]
        iters = state.get("iter", 0)
        started_at = state.get("started_at", 0)
        mode = state.get("mode", "cli")
        running_cost = state.get("running_cost", 0.0)
        elapsed = int(time.time() - started_at) if started_at else 0

        badge_class = status if status in ("running", "completed", "blocked", "timeout", "stopped") else "stopped"

        def _row(label, val):
            return (f"<div class='row'><span class='label'>{label}</span>"
                    f"<span class='value'>{val}</span></div>")

        rows = [
            _row("Status", f"<span class='status-badge {badge_class}'>{status}</span>"),
            _row("Goal", goal),
            _row("Mode", mode),
            _row("Iterations", str(iters)),
            _row("Elapsed", f"{elapsed}s"),
        ]
        if running_cost > 0:
            rows.append(_row("Cost", f"${running_cost:.2f}"))

        card = f"<div class='card'><h2>Run Status</h2>{''.join(rows)}</div>"

        if summary_text:
            card += f"<div class='card'><h2>Summary</h2><pre>{summary_text}</pre></div>"

        return html_page + card + "<div class='footer'>AgentLoop Monitor</div></body></html>"

    class _Handler(BaseHTTPRequestHandler):
        """HTTP request handler for the monitoring UI."""
        def do_GET(self) -> None:
            try:
                page = _render_status()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page.encode("utf-8"))
            except Exception:
                self.send_response(500)
                self.end_headers()

        def log_message(self, fmt, *args) -> None:
            log(f"web: {fmt % args}")

    server = HTTPServer(("0.0.0.0", port), _Handler)
    log(f"web monitor started at http://0.0.0.0:{port}")
    log("press Ctrl+C to stop the monitor")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("web monitor stopped")
        server.server_close()
    return EXIT_COMPLETED


# ============================================================================
# MULTI-AGENT FAN-OUT
# ============================================================================
def cmd_run_plan(args: argparse.Namespace) -> int:
    """Parse a plan.md file and spawn sub-loops for each task."""
    plan_path = pathlib.Path(args.run)
    if not plan_path.exists():
        log(f"ERROR: plan file not found: {plan_path}")
        return EXIT_CONFIG

    tasks = _parse_plan(plan_path.read_text())
    if not tasks:
        log("ERROR: no tasks found in plan file. Use `- [ ] task description` format.")
        return EXIT_CONFIG

    log(f"Parsed {len(tasks)} tasks from {plan_path.name}")
    results: list[dict] = []
    all_ok = True

    for i, task in enumerate(tasks):
        log(f"[{i + 1}/{len(tasks)}] Starting task: {task[:80]}...")

        # Launch a subprocess for this task
        verify = args.verify or os.environ.get("VERIFY_CMD", "")
        harness = args.harness or os.environ.get("AGENT_PRESET", "")
        agent_cmd = args.agent_cmd or os.environ.get("AGENT_CMD", "")

        cmd_parts = [sys.executable, "-m", "agentloop", task]
        if verify:
            cmd_parts.extend(["--verify", verify])
        if harness:
            cmd_parts.extend(["--harness", harness])
        if agent_cmd:
            cmd_parts.extend(["--agent-cmd", agent_cmd])

        try:
            r = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=args.timeout or 3600)
            task_ok = r.returncode == 0
            results.append({
                "task": task,
                "returncode": r.returncode,
                "passed": task_ok,
                "output": (r.stdout or "")[:500] + (r.stderr or "")[:500],
            })
        except subprocess.TimeoutExpired:
            results.append({
                "task": task,
                "returncode": -1,
                "passed": False,
                "output": "TIMEOUT",
            })
        except Exception as e:
            results.append({
                "task": task,
                "returncode": -2,
                "passed": False,
                "output": str(e),
            })

        if not results[-1]["passed"]:
            all_ok = False
            log(f"[{i + 1}/{len(tasks)}] FAILED: {task[:60]}...")
        else:
            log(f"[{i + 1}/{len(tasks)}] PASSED: {task[:60]}...")

    # Print summary
    print("\n" + "=" * 60)
    print("  Multi-Agent Run Summary")
    print("=" * 60)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"  Tasks: {passed}/{total} passed")
    for i, r in enumerate(results):
        icon = "✅" if r["passed"] else "❌"
        print(f"  {icon} [{i + 1}] ({r['returncode']}) {r['task'][:70]}")
    print("=" * 60)

    return EXIT_COMPLETED if all_ok else EXIT_BLOCKED


def _parse_plan(text: str) -> list[str]:
    """Extract task lines from a markdown plan file.
    
    Recognizes:
    - `- [ ] task` (GitHub-style checklist)
    - `## task` (heading as task)\n    - `- task` (bullet point)
    """
    tasks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        # GitHub checklist: - [ ] task
        if line.startswith("- [ ]"):
            tasks.append(line[5:].strip())
        # Bullet: - task or * task
        elif line.startswith("- ") or line.startswith("* "):
            tasks.append(line[2:].strip())
        # Task heading: ## task
        elif line.startswith("## ") and not line.startswith("###"):
            tasks.append(line[3:].strip())
    return [t for t in tasks if t and not t.startswith("#") and len(t) > 3]


# ============================================================================
# SCAFFOLD
# ============================================================================
def _scaffold(args: argparse.Namespace) -> None:
    """Create goal.txt / verify.sh / .env for a first run, then exit."""
    if args.goal:
        GOAL_FILE.write_text(args.goal + "\n")
    elif not GOAL_FILE.exists():
        GOAL_FILE.write_text("Describe the task the agent should complete and verify here.\n")
    if not (ROOT / "verify.sh").exists() and (ROOT / "verify_template.sh").exists():
        shutil.copy(ROOT / "verify_template.sh", ROOT / "verify.sh")
        os.chmod(ROOT / "verify.sh", 0o755)
    env_path = ROOT / ".env"
    if not env_path.exists():
        preset = args.harness or "opencode"
        env_path.write_text(
            f"AGENT_MODE=cli\nAGENT_PRESET={preset}\nVERIFY_CMD=\"bash verify.sh\"\n")
    print("Scaffolded: goal.txt, verify.sh, .env")
    print("Edit verify.sh to assert correctness, then:  agentloop --dry-run")
    print("Launch:  ./launch.sh   |   or one-shot:  agentloop \"your goal\" --verify \"bash verify.sh\"")


# ============================================================================
# MAIN
# ============================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="agentloop",
        description="Harness-agnostic, self-verifying autonomy wrapper for coding agents.")
    ap.add_argument("goal", nargs="?", help="task text (writes goal.txt; overrides the file)")
    ap.add_argument("--verify", help="set VERIFY_CMD — the verification oracle command")
    ap.add_argument("--harness", help="preset: opencode|kilocode|claude|aider|codex|goose")
    ap.add_argument("--agent-cmd", help="explicit agent command (overrides --harness)")
    ap.add_argument("--mode", help="cli (default) | direct")
    ap.add_argument("--max-iters", type=int, help="max loop iterations")
    ap.add_argument("--wall", type=int, help="wall-clock limit in seconds")
    ap.add_argument("--step-delay", type=float, help="delay between iterations (s)")
    ap.add_argument("--max-cost", type=float, help="max cost in USD (cost cap)")
    ap.add_argument("--init", action="store_true",
                    help="scaffold goal.txt + verify.sh + .env, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the resolved configuration and exit (no loop)")
    ap.add_argument("--version", action="version", version=f"agentloop {__version__}")

    # Subcommands as optional flags (avoids positional arg conflicts with goal)
    ap.add_argument("--status", action="store_true", help="show current run status")
    ap.add_argument("--serve", action="store_true", help="start web monitoring UI")
    ap.add_argument("--port", type=int, default=8080, help="HTTP port for --serve (default 8080)")
    ap.add_argument("--run", type=str, default=None, metavar="PLAN.md",
                     help="run tasks from a plan.md file (multi-agent)")
    ap.add_argument("--timeout", type=int, default=3600, help="per-task timeout for --run (seconds)")

    args = ap.parse_args(argv)

    # Handle subcommands-as-flags
    if args.status:
        return cmd_status(args)
    if args.serve:
        return cmd_serve(args)
    if args.run:
        return cmd_run_plan(args)

    if args.init:
        _scaffold(args)
        return EXIT_COMPLETED

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
    if args.max_cost is not None:
        os.environ["MAX_COST_USD"] = str(args.max_cost)
    read_config()
    _validate_config()

    goal = (args.goal if args.goal
            else (GOAL_FILE.read_text().strip() if GOAL_FILE.exists() else "No goal set."))
    goal = _validate_goal(goal)

    if args.dry_run:
        cmd = resolve_agent_cmd()
        print("mode      :", AGENT_MODE)
        print("agent_cmd :", cmd or "(none resolved — set --harness/--agent-cmd)")
        print("verify    :", os.environ.get("VERIFY_CMD", "(none)"))
        print("goal      :", goal[:120])
        print("max_iters :", MAX_ITERS)
        print("wall_sec  :", WALL_CLOCK_SEC)
        print("max_cost  :", f"${MAX_COST_USD:.2f}" if MAX_COST_USD > 0 else "unlimited")
        print("version   :", __version__)
        return EXIT_COMPLETED

    if args.goal:
        GOAL_FILE.write_text(args.goal + "\n")

    _install_signal_handlers()
    try:
        atomic_write(PID_FILE, str(os.getpid()) + "\n")
    except Exception:
        PID_FILE.write_text(str(os.getpid()))
    log(f"started | mode={AGENT_MODE} | version={__version__} | sandbox={SANDBOX} | pid={os.getpid()}")
    try:
        if AGENT_MODE == "direct":
            status = run_direct_mode(goal)
        else:
            status = run_cli_mode(goal)
    finally:
        PID_FILE.unlink(missing_ok=True)
        log("stopped.")

    return _STATUS_EXIT.get(status, EXIT_STOPPED)


def cli() -> None:
    """Console-script entry point for setuptools."""
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
