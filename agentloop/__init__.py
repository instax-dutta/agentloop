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
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import RotatingFileHandler
from typing import Any

from .cost import CostTracker, parse_harness_output
from .docker import run_in_docker
from .oracle import DATA_DIR, ROOT, gate_done, run_verify, safe_env, verify_passed
from .parallel import TaskNode, parse_plan_dag, run_plan_parallel
from .telemetry import LangfuseExporter, TelemetryExporter, is_any_telemetry_enabled

# ---- telemetry (optional; no-op when unconfigured) --------------------------
_telemetry = TelemetryExporter()
_langfuse = LangfuseExporter()


def _goal_hash(goal: str) -> str:
    """Short stable hash of the goal for telemetry attributes."""
    import hashlib

    return hashlib.sha256(goal.encode()).hexdigest()[:12]

try:
    from importlib.metadata import version as _v
    __version__ = _v("agentloop-cli")
except Exception:
    __version__ = "0.5.0.dev0"

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
# All paths are overridable via env vars so parallel multi-agent workers can
# keep per-task sandboxes and namespaced state/log/pid files.
def _env_path(name: str, default: pathlib.Path) -> pathlib.Path:
    val = os.environ.get(name, "")
    return pathlib.Path(val).expanduser() if val else default


SANDBOX = _env_path("AGENTLOOP_SANDBOX", ROOT / "sandbox")
GOAL_FILE = _env_path("AGENTLOOP_GOAL_FILE", ROOT / "goal.txt")
STOP_FILE = _env_path("AGENTLOOP_STOP_FILE", ROOT / "STOP")
PID_FILE = _env_path("AGENTLOOP_PID_FILE", ROOT / "agentloop.pid")
LOG_FILE = _env_path("AGENTLOOP_LOG_FILE", ROOT / "agentloop.log")
STATE_FILE = _env_path("AGENTLOOP_STATE_FILE", ROOT / "agentloop.state.json")
SUMMARY_FILE = _env_path("AGENTLOOP_SUMMARY_FILE", ROOT / "agentloop.summary.txt")

# ---- config (env-overridable) ----------------------------------------------
AGENT_MODE = os.environ.get("AGENT_MODE", "cli").lower()
AGENT_PRESET = os.environ.get("AGENT_PRESET", "")
AGENT_CMD = os.environ.get("AGENT_CMD", "")
MAX_ITERS = int(os.environ.get("MAX_ITERS", "50"))
WALL_CLOCK_SEC = int(os.environ.get("WALL_CLOCK_SEC", str(6 * 3600)))
STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "900"))
USE_DOCKER = os.environ.get("USE_DOCKER", "").lower() in ("1", "true", "yes")
USE_PODMAN = os.environ.get("USE_PODMAN", "").lower() in ("1", "true", "yes")

# --- cost cap ---------------------------------------------------------------
MAX_COST_USD = float(os.environ.get("MAX_COST_USD", "0"))
ESTIMATED_COST_PER_ITER = float(os.environ.get("ESTIMATED_COST_PER_ITER", "0.10"))

# --- logging ----------------------------------------------------------------
LOG_MAX_MB = int(os.environ.get("LOG_MAX_MB", "10"))
LOG_JSON = os.environ.get("LOG_JSON", "").lower() in ("1", "true", "yes")

# --- notifications ----------------------------------------------------------
NOTIFY_TELEGRAM_BOT_TOKEN = os.environ.get("NOTIFY_TELEGRAM_BOT_TOKEN", "")
NOTIFY_TELEGRAM_CHAT_ID = os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", "")
NOTIFY_DISCORD_WEBHOOK_URL = os.environ.get("NOTIFY_DISCORD_WEBHOOK_URL", "")
NOTIFY_SLACK_WEBHOOK_URL = os.environ.get("NOTIFY_SLACK_WEBHOOK_URL", "")


def _get_direct_config() -> tuple[str | None, str, str]:
    api_key = os.environ.get("AGENTLOOP_API_KEY")
    if not api_key:
        api_key = os.environ.get("KILO_API_KEY") or os.environ.get("KILOCODE_API_KEY")
        if api_key:
            logging.getLogger("agentloop").warning(
                "KILO_API_KEY/KILOCODE_API_KEY is deprecated; use AGENTLOOP_API_KEY instead."
            )
    base_url = (
        os.environ.get("AGENTLOOP_BASE_URL")
        or os.environ.get("KILO_BASE_URL")
        or "https://api.openai.com/v1"
    )
    model = (
        os.environ.get("AGENTLOOP_MODEL")
        or os.environ.get("KILO_MODEL")
        or "gpt-4o-mini"
    )
    return api_key, base_url, model


# direct-mode (legacy) config
API_KEY, BASE_URL, MODEL = _get_direct_config()
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


def _to_float(val: Any, default: float = 0.0) -> float:
    """Coerce a state-file value to float without crashing on bad data."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def log(msg: str) -> None:
    """Log a timestamped line to both the rotating log file and stdout.

    When LOG_JSON=true, emit a single JSON line per record so logs can be
    ingested by Loki / Elastic / CloudWatch / jq.
    """
    global _logger_initialized
    if not _logger_initialized:
        _init_logger()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if LOG_JSON:
        record = json.dumps({"ts": ts, "level": "info", "msg": msg}, ensure_ascii=False)
        print(record, flush=True)
    else:
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
        NOTIFY_DISCORD_WEBHOOK_URL, NOTIFY_SLACK_WEBHOOK_URL, USE_DOCKER, USE_PODMAN, \
        LOG_JSON
    AGENT_MODE = os.environ.get("AGENT_MODE", "cli").lower()
    AGENT_PRESET = os.environ.get("AGENT_PRESET", "")
    AGENT_CMD = os.environ.get("AGENT_CMD", "")
    MAX_ITERS = int(os.environ.get("MAX_ITERS", "50"))
    WALL_CLOCK_SEC = int(os.environ.get("WALL_CLOCK_SEC", str(6 * 3600)))
    STEP_DELAY = float(os.environ.get("STEP_DELAY", "3"))
    AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "900"))
    USE_DOCKER = os.environ.get("USE_DOCKER", "").lower() in ("1", "true", "yes")
    USE_PODMAN = os.environ.get("USE_PODMAN", "").lower() in ("1", "true", "yes")
    MAX_COST_USD = float(os.environ.get("MAX_COST_USD", "0"))
    ESTIMATED_COST_PER_ITER = float(os.environ.get("ESTIMATED_COST_PER_ITER", "0.10"))
    LOG_MAX_MB = int(os.environ.get("LOG_MAX_MB", "10"))
    LOG_JSON = os.environ.get("LOG_JSON", "").lower() in ("1", "true", "yes")
    NOTIFY_TELEGRAM_BOT_TOKEN = os.environ.get("NOTIFY_TELEGRAM_BOT_TOKEN", "")
    NOTIFY_TELEGRAM_CHAT_ID = os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", "")
    NOTIFY_DISCORD_WEBHOOK_URL = os.environ.get("NOTIFY_DISCORD_WEBHOOK_URL", "")
    NOTIFY_SLACK_WEBHOOK_URL = os.environ.get("NOTIFY_SLACK_WEBHOOK_URL", "")
    DIRECT_MAX_STEPS = int(os.environ.get("MAX_STEPS", "300"))
    DIRECT_MSG_CAP = int(os.environ.get("MSG_CAP", "120"))
    API_KEY, BASE_URL, MODEL = _get_direct_config()


# ---- run state (crash-safe resume) -----------------------------------------
def load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state: dict[str, Any]) -> None:
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
    prev = load_state()
    state: dict[str, Any] = {
        "goal": goal, "mode": AGENT_MODE, "iter": it_next,
        "feedback": [], "started_at": started_at, "status": status,
        "running_cost": running_cost,
    }
    # Preserve the cost breakdown so --cost / --status / the web UI can show
    # the per-iteration history after the run finishes.
    if isinstance(prev.get("cost_breakdown"), dict):
        state["cost_breakdown"] = prev["cost_breakdown"]
    save_state(state)
    write_summary(status, iters, started_at, goal, running_cost)


def _install_signal_handlers() -> None:
    """On SIGTERM/SIGINT, create STOP so the loop exits cleanly with a summary."""
    def _handler(signum: int, _frame: Any) -> None:
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
        log("ERROR: goal is empty. Fix: pass a goal argument (e.g. `agentloop 'build a linter'`), "
            "write one to goal.txt, or run `agentloop --init` to scaffold a starter goal.")
        sys.exit(EXIT_CONFIG)
    goal = goal.strip()
    if len(goal) > 10000:
        log("WARNING: goal exceeds 10000 characters, truncating.")
        goal = goal[:10000]

    blocked_env = os.environ.get("BLOCKED_GOAL_PATTERNS", "").strip()
    if blocked_env:
        patterns = [p.strip() for item in blocked_env.split(":") for p in item.split(",") if p.strip()]
        for pat in patterns:
            if pat.lower() in goal.lower():
                log(f"ERROR: goal contains blocked pattern: {pat!r}. "
                    "Fix: remove the pattern from your goal, or unset BLOCKED_GOAL_PATTERNS in .env "
                    "if this block is not intended.")
                sys.exit(EXIT_CONFIG)

    # Warn about potentially dangerous content
    dangerous = ["rm -rf", "sudo ", "chmod 777", "> /dev/sda"]
    for d in dangerous:
        if d in goal.lower():
            log(f"WARNING: goal contains potentially dangerous pattern: {d!r}")
    return goal


def _validate_config() -> None:
    """Validate runtime configuration values."""
    if MAX_ITERS < 1:
        log("ERROR: MAX_ITERS must be >= 1. Fix: set MAX_ITERS=50 (or any value >= 1) in .env.")
        sys.exit(EXIT_CONFIG)
    if WALL_CLOCK_SEC < 1:
        log("ERROR: WALL_CLOCK_SEC must be >= 1. Fix: set WALL_CLOCK_SEC=21600 in .env.")
        sys.exit(EXIT_CONFIG)
    if STEP_DELAY < 0:
        log("ERROR: STEP_DELAY must be >= 0. Fix: set STEP_DELAY=3 in .env.")
        sys.exit(EXIT_CONFIG)
    if AGENT_TIMEOUT < 1:
        log("ERROR: AGENT_TIMEOUT must be >= 1. Fix: set AGENT_TIMEOUT=900 in .env.")
        sys.exit(EXIT_CONFIG)
    if MAX_COST_USD < 0:
        log("ERROR: MAX_COST_USD must be >= 0. Fix: set MAX_COST_USD=5.0 or unset it in .env.")
        sys.exit(EXIT_CONFIG)
    if LOG_MAX_MB < 1:
        log("ERROR: LOG_MAX_MB must be >= 1. Fix: set LOG_MAX_MB=10 in .env.")
        sys.exit(EXIT_CONFIG)


# ============================================================================
# CLI MODE — drive an external coding-agent CLI in a verify/retry loop
# ============================================================================
def build_prompt(goal: str, feedback: list[str], cost_info: str = "", remaining_budget: float = -1.0) -> str:
    p = (
        "You are a coding agent working AUTONOMOUSLY. There is NO human in the loop — "
        "never ask for clarification or confirmation; just act.\n"
        f"GOAL:\n{goal}\n\n"
        "Work ONLY inside the current working directory (the sandbox). Use your tools to "
        "implement and test the goal. Do NOT modify any verify/check script outside the sandbox.\n"
    )
    if MAX_COST_USD > 0 and remaining_budget >= 0 and remaining_budget < ESTIMATED_COST_PER_ITER * 2:
        p += (f"\nBUDGET CRITICAL: ${remaining_budget:.2f} remaining. "
              "Aim for minimal, surgical changes. Do not regenerate large files.\n")
    elif cost_info:
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
        cost_tracker = CostTracker.from_dict(prev.get("cost_breakdown", {}))
        log(f"resuming from iter {it_start} (cost so far: ${running_cost:.2f})")
    else:
        it_start = 1
        feedback = []
        started_at = time.time()
        running_cost = 0.0
        cost_tracker = CostTracker()

    save_state({
        "goal": goal, "mode": "cli", "iter": it_start,
        "feedback": feedback, "started_at": started_at, "status": "running",
        "running_cost": running_cost,
        "cost_breakdown": cost_tracker.to_dict(),
    })

    ran = 0

    def _end_iter(outcome: str) -> None:
        """Close the telemetry span for the current iteration."""
        _telemetry.record_event("iteration.end", {"outcome": outcome})
        _telemetry.finish_span()

    for it in range(it_start, MAX_ITERS + 1):
        ran += 1

        # --- telemetry span for this iteration ---
        _telemetry.start_span(f"agentloop.iter.{it}", {
            "iter": str(it),
            "preset": AGENT_PRESET or resolve_agent_cmd(),
            "goal_hash": _goal_hash(goal),
            "mode": "cli",
        })

        # --- STOP file check ---
        if STOP_FILE.exists():
            log("STOP file detected — halting.")
            _end_iter("stopped")
            finish("stopped", ran, started_at, goal, it + 1, running_cost)
            return "stopped"

        # --- Wall-clock check (absolute from run start, survives resume) ---
        if time.time() - started_at > WALL_CLOCK_SEC:
            log("wall-clock limit reached — halting.")
            _end_iter("timeout")
            finish("timeout", ran, started_at, goal, it + 1, running_cost)
            return "timeout"

        # --- Cost cap check ---
        if MAX_COST_USD > 0 and running_cost > MAX_COST_USD:
            log(f"cost cap exceeded (${running_cost:.2f} > ${MAX_COST_USD:.2f}) — halting.")
            _end_iter("over-budget")
            finish("over-budget", ran, started_at, goal, it + 1, running_cost)
            return "over-budget"

        cost_info = ""
        remaining = MAX_COST_USD - running_cost if MAX_COST_USD > 0 else -1.0
        if MAX_COST_USD > 0:
            if it == it_start:
                log("WARN: cost in CLI mode is estimated at "
                    f"${ESTIMATED_COST_PER_ITER:.2f}/iter — direct mode tracks real token usage")
            cost_info = f"running cost ${running_cost:.2f}, remaining budget ${remaining:.2f}"

        prompt = build_prompt(goal, feedback, cost_info, remaining_budget=remaining)
        env = safe_env()
        env["AGENTLOOP_PROMPT"] = prompt
        try:
            if USE_DOCKER or USE_PODMAN:
                r = run_in_docker(cmd, SANDBOX, env=env, timeout=AGENT_TIMEOUT, podman=USE_PODMAN)
            else:
                r = subprocess.run(cmd, shell=True, cwd=str(SANDBOX), env=env,
                                   capture_output=True, text=True, timeout=AGENT_TIMEOUT)
            rc_agent = r.returncode
            out = (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            rc_agent = None
            out = f"AGENT TIMEOUT after {AGENT_TIMEOUT}s"
            log(out)

        log(f"iter {it}: agent exit={rc_agent} -> {out[:200]!r}")

        # Cost tracking
        parsed_usage = parse_harness_output(AGENT_PRESET or resolve_agent_cmd(), out)
        if parsed_usage:
            in_tok, out_tok, m_name = parsed_usage
            iter_data = cost_tracker.record_iteration(
                iter_num=it,
                preset=AGENT_PRESET or resolve_agent_cmd(),
                input_tokens=in_tok,
                output_tokens=out_tok,
                model_name=m_name,
                estimated_fallback_cost=ESTIMATED_COST_PER_ITER,
            )
            running_cost = cost_tracker.running_cost
            log(f"iter {it}: cost ${iter_data['cost']:.4f} "
                f"(input={in_tok} tok, output={out_tok} tok, model={iter_data['model']})")
        else:
            iter_data = cost_tracker.record_iteration(
                iter_num=it,
                preset=AGENT_PRESET or resolve_agent_cmd(),
                estimated_fallback_cost=ESTIMATED_COST_PER_ITER,
            )
            running_cost = cost_tracker.running_cost

        git_checkpoint(SANDBOX, f"iter {it}")

        verify_passed_bool: bool | None = None
        if os.environ.get("VERIFY_CMD"):
            passed, vout = verify_passed(ROOT)
            verify_passed_bool = passed
            if passed:
                log(f"iter {it}: VERIFICATION PASSED — task complete.")
                print_final(SANDBOX)
                _end_iter("completed")
                finish("completed", ran, started_at, goal, it + 1, running_cost)
                return "completed"
            log(f"iter {it}: VERIFICATION FAILED — feeding results back to agent.")
            feedback.append(vout)
            feedback = feedback[-2:]
        else:
            if terminal_token(out, "BLOCKED"):
                log("agent reported BLOCKED.")
                _end_iter("blocked")
                finish("blocked", ran, started_at, goal, it + 1, running_cost)
                return "blocked"
            if terminal_token(out, "DONE"):
                log("agent reported DONE (no verifier configured).")
                _end_iter("completed")
                finish("completed", ran, started_at, goal, it + 1, running_cost)
                return "completed"

        _telemetry.record_event("iteration.result", {
            "verify_passed": str(bool(verify_passed_bool)),
            "agent_exit": str(rc_agent),
        })
        save_state({
            "goal": goal, "mode": "cli", "iter": it + 1,
            "feedback": feedback, "started_at": started_at, "status": "running",
            "running_cost": running_cost,
            "cost_breakdown": cost_tracker.to_dict(),
        })
        _end_iter("retry")
        time.sleep(STEP_DELAY)

    finish("exhausted", ran, started_at, goal, MAX_ITERS + 1, running_cost)
    return "exhausted"


# ============================================================================
# DIRECT MODE (legacy) — call an OpenAI-compatible API directly, one thread
# ============================================================================
def run_direct_mode(goal: str) -> str:
    if not API_KEY:
        log("ERROR: direct mode needs AGENTLOOP_API_KEY (legacy KILO_API_KEY also works). "
            "Fix: add AGENTLOOP_API_KEY=sk-... to .env, or switch to AGENT_MODE=cli with a real harness.")
        sys.exit(EXIT_CONFIG)
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
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
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        }},
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read a file relative to the sandbox.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {
            "name": "list_dir",
            "description": "List a sandbox directory (default: current).",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    ]
    dispatch: dict[str, Callable[..., str]] = {"run_shell": run_shell, "write_file": write_file,
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
        _telemetry.start_span(f"agentloop.step.{step}", {
            "iter": str(step),
            "preset": "direct",
            "goal_hash": _goal_hash(goal),
            "mode": "direct",
        })
        if STOP_FILE.exists():
            log("STOP file detected — halting.")
            status = "stopped"
            _telemetry.finish_span()
            break
        if time.time() - start > WALL_CLOCK_SEC:
            log("wall-clock limit reached — halting.")
            status = "timeout"
            _telemetry.finish_span()
            break
        if MAX_COST_USD > 0 and running_cost > MAX_COST_USD:
            log(f"cost cap exceeded (${running_cost:.2f} > ${MAX_COST_USD:.2f}) — halting.")
            status = "over-budget"
            _telemetry.finish_span()
            break

        if len(messages) > DIRECT_MSG_CAP + 2:
            messages = [messages[0], messages[1]] + messages[-DIRECT_MSG_CAP:]
            log(f"compaction: history trimmed to {len(messages)} messages")

        try:
            r = client.chat.completions.create(model=MODEL, messages=messages, tools=tools)
            delay = STEP_DELAY
        except Exception as e:
            _telemetry.finish_span()
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
                _telemetry.finish_span()
                break
            time.sleep(delay)
            _telemetry.finish_span()
            continue
        if terminal_token(text, "BLOCKED") or text.strip() == "BLOCKED":
            log("agent reported BLOCKED.")
            status = "blocked"
            _telemetry.finish_span()
            break

        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            reflect_streak += 1
            if reflect_streak >= 3:
                log("agent reflected 3x in a row without tools — assuming stuck, halting.")
                status = "exhausted"
                _telemetry.finish_span()
                break
            if reflect_streak == 1:
                nudge = ("You must take a concrete action using a tool now. Do not ask questions. "
                         "If the goal is already met, reply exactly DONE.")
            else:
                nudge = ("FINAL: call a tool to make progress, or reply exactly DONE. "
                         "No questions allowed.")
            messages.append({"role": "user", "content": nudge})
            log(f"step {step}: (reflection #{reflect_streak}) {text[:100]!r}")
            _telemetry.finish_span()
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
        _telemetry.record_event("step.end", {"step": str(step), "cost": f"{running_cost:.4f}"})
        _telemetry.finish_span()
        time.sleep(delay)

    _telemetry.finish_span()
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
            cost_data = state.get("cost_breakdown", {})
            if isinstance(cost_data, dict):
                for item in cost_data.get("by_iter", [])[:10]:
                    est = " (est)" if item.get("is_estimated") else ""
                    print(f"    - iter {item.get('iter')}: ${_to_float(item.get('cost')):.4f} "
                          f"model={item.get('model')}{est}")
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


def _render_status_page() -> str:
    """Render the full monitor HTML page from the current run state.

    Extracted from cmd_serve so tests can assert on the HTML — including the
    cost breakdown card — without binding a port.
    """
    html_page = textwrap.dedent("""    <!DOCTYPE html>
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
      .bars { margin-top:0.8rem; }
      .bar-row { display:flex; align-items:center; gap:0.6rem; padding:0.2rem 0; }
      .bar-label { color:#8b949e; font-size:0.8rem; width:4.5rem; text-align:right; }
      .bar-track { flex:1; background:#21262d; border-radius:4px; height:12px; overflow:hidden; }
      .bar-fill { height:100%; background:#58a6ff; border-radius:4px; transition:width 0.3s ease; }
      .bar-val { color:#f0f6fc; font-size:0.8rem; width:6.5rem; }
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

    state = load_state()
    summary_text = ""
    try:
        summary_text = SUMMARY_FILE.read_text().strip()
    except Exception:
        pass

    if not state:
        return html_page + ("<div class='card'><h2>No runs found</h2></div>"
                            + "<div class='footer'>AgentLoop Monitor</div></body></html>")

    status = state.get("status", "unknown")
    goal = state.get("goal", "")[:100]
    iters = state.get("iter", 0)
    started_at = state.get("started_at", 0)
    mode = state.get("mode", "cli")
    running_cost = state.get("running_cost", 0.0)
    elapsed = int(time.time() - started_at) if started_at else 0

    badge_class = status if status in ("running", "completed", "blocked", "timeout", "stopped") else "stopped"

    def _row(label: str, val: str) -> str:
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

    # Cost breakdown card (plain HTML/CSS bars — no JS deps)
    cost_card = ""
    cost_data = state.get("cost_breakdown", {})
    if isinstance(cost_data, dict):
        by_iter = cost_data.get("by_iter", [])
        if by_iter:
            max_cost = max((_to_float(i.get("cost")) for i in by_iter), default=1.0)
            if max_cost <= 0:
                max_cost = 1.0
            bars = []
            model_totals: dict[str, float] = {}
            for item in by_iter:
                c = _to_float(item.get("cost"))
                model = str(item.get("model") or "unknown")
                model_totals[model] = model_totals.get(model, 0.0) + c
                est = " (est)" if item.get("is_estimated") else ""
                pct = (c / max_cost) * 100
                bars.append(
                    f"<div class='bar-row'><span class='bar-label'>iter {item.get('iter')}</span>"
                    f"<div class='bar-track'><div class='bar-fill' style='width:{pct:.0f}%'></div></div>"
                    f"<span class='bar-val'>${c:.4f}{est}</span></div>")
            model_rows = "".join(
                _row(m, f"${v:.4f}") for m, v in sorted(model_totals.items(), key=lambda kv: -kv[1]))
            total_cost = float(cost_data.get("running_cost", 0) or 0)
            cost_card = (
                f"<div class='card'><h2>Cost Breakdown</h2>"
                f"{_row('Total', f'${total_cost:.4f}')}"
                f"<div class='bars'>{''.join(bars)}</div>"
                f"<h3 style='margin-top:0.8rem;font-size:0.95rem;color:#f0f6fc;'>By model</h3>"
                f"{model_rows}</div>")

    return html_page + card + cost_card + "<div class='footer'>AgentLoop Monitor</div></body></html>"


class _MonitorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the monitoring UI."""

    def do_GET(self) -> None:
        try:
            page = _render_status_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        except Exception:
            self.send_response(500)
            self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        log(f"web: {fmt % args}")


def cmd_serve(args: argparse.Namespace) -> int:
    """Start a tiny web server showing run status."""
    port = args.port if args.port else 8080
    server = HTTPServer(("0.0.0.0", port), _MonitorHandler)
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
    """Parse a plan.md file and spawn sub-loops for each task — in parallel.

    Recognizes `- [ ] task`, `- task`, `* task`, and `## task` formats, plus
    DAG dependencies via `(after: #N)` / `(depends on: #N)` annotations.
    Each task runs in its own sandbox + namespaced state/log/pid files, so
    independent tasks never clobber each other, and tasks whose dependency
    failed are skipped (never started).
    """
    plan_path = pathlib.Path(args.run)
    if not plan_path.exists():
        log(f"ERROR: plan file not found: {plan_path}\n"
            "Fix: run from the project root and use a path relative to it, "
            "e.g. `agentloop --run plan.md`.")
        return EXIT_CONFIG

    text = plan_path.read_text()
    nodes = parse_plan_dag(text)
    if not nodes:
        log("ERROR: no tasks found in plan file. Use `- [ ] task description` format.\n"
            "Fix: check the file contains at least one checkbox/bullet/heading task.")
        return EXIT_CONFIG

    verify = args.verify or os.environ.get("VERIFY_CMD", "")
    harness = args.harness or os.environ.get("AGENT_PRESET", "")
    agent_cmd = args.agent_cmd or os.environ.get("AGENT_CMD", "")
    workers = args.workers if getattr(args, "workers", None) else min(4, len(nodes))

    log(f"Parsed {len(nodes)} tasks from {plan_path.name} (workers={workers})")

    def worker_fn(node: TaskNode, sandbox_dir: pathlib.Path, state_file: pathlib.Path) -> int:
        """Run one plan task as an isolated agentloop subprocess."""
        cmd_parts = [sys.executable, "-m", "agentloop", node.name]
        if verify:
            cmd_parts.extend(["--verify", verify])
        if harness:
            cmd_parts.extend(["--harness", harness])
        if agent_cmd:
            cmd_parts.extend(["--agent-cmd", agent_cmd])

        env = os.environ.copy()
        state_s = str(state_file)
        stem = state_s[:-5] if state_s.endswith(".json") else state_s  # strip .json
        env["AGENTLOOP_SANDBOX"] = str(sandbox_dir)
        env["AGENTLOOP_STATE_FILE"] = state_s
        env["AGENTLOOP_GOAL_FILE"] = str(pathlib.Path(state_s).with_name(f"goal.task-{node.task_id}.txt"))
        env["AGENTLOOP_LOG_FILE"] = stem.replace("agentloop.state", "agentloop.log")
        env["AGENTLOOP_PID_FILE"] = stem.replace("agentloop.state", "agentloop.pid")
        env["AGENTLOOP_SUMMARY_FILE"] = stem.replace("agentloop.state", "agentloop.summary")
        try:
            r = subprocess.run(cmd_parts, capture_output=True, text=True,
                               timeout=args.timeout or 3600, env=env)
            return r.returncode
        except subprocess.TimeoutExpired:
            log(f"task {node.task_id} timed out after {(args.timeout or 3600)}s")
            return -1
        except Exception as e:
            log(f"task {node.task_id} crashed: {e}")
            return -2

    results = run_plan_parallel(nodes, worker_fn, max_workers=workers)

    # Print summary
    print("\n" + "=" * 60)
    print("  Multi-Agent Run Summary")
    print("=" * 60)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"  Tasks: {passed}/{total} passed")
    for r in results:
        if r["passed"]:
            icon = "✅"
        elif r.get("skipped"):
            icon = "⏭️"
        else:
            icon = "❌"
        print(f"  {icon} [{r['task_id']}] ({r['returncode']}) {r['name'][:70]}")
    print("=" * 60)

    return EXIT_COMPLETED if passed == total else EXIT_BLOCKED


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
    cwd = pathlib.Path.cwd()
    goal_file = cwd / "goal.txt"
    verify_file = cwd / "verify.sh"
    env_file = cwd / ".env"

    # Determine example to seed from
    example_dir = None
    if args.example:
        example_dir = DATA_DIR / "examples" / args.example
        if not example_dir.exists():
            print(f"ERROR: example {args.example!r} not found")
            available = [d.name for d in (DATA_DIR / "examples").iterdir() if d.is_dir()]
            print(f"Available: {', '.join(sorted(available))}")
            return

    if example_dir:
        goal_src = example_dir / "goal.txt"
        verify_src = example_dir / "verify.sh"
        if goal_src.exists():
            shutil.copy(goal_src, goal_file)
        if verify_src.exists():
            shutil.copy(verify_src, verify_file)
            os.chmod(verify_file, 0o755)
        print(f"Seeded from example: {args.example}")
    else:
        if args.goal:
            goal_file.write_text(args.goal + "\n")
        elif not goal_file.exists():
            goal_file.write_text(
                "Create a Python script called hello.py that prints Hello, AgentLoop! to stdout\n")

        if not verify_file.exists():
            verify_file.write_text(
                '#!/usr/bin/env bash\n'
                '# Verification oracle for AgentLoop.\n'
                '# Exit 0 if the goal is met. Exit non-zero if not.\n'
                'set -u\n'
                'cd "$(dirname "$0")/sandbox" || exit 2\n'
                'if [ -f hello.py ]; then\n'
                '  python3 hello.py | grep -q "Hello, AgentLoop!" && exit 0\n'
                'fi\n'
                'echo "hello.py not found or incorrect output"\n'
                'exit 1\n'
            )
            os.chmod(verify_file, 0o755)

    if not env_file.exists():
        preset = args.harness or "opencode"
        env_file.write_text(
            f"AGENT_MODE=cli\nAGENT_PRESET={preset}\nVERIFY_CMD=\"bash verify.sh\"\n")

    print("Scaffolded: goal.txt, verify.sh, .env")
    print()
    print("  Next steps:")
    print("    agentloop --dry-run                            # preview config")
    print('    agentloop --verify "bash verify.sh"           # run once')


# ============================================================================
# MAIN
# ============================================================================
def cmd_cost(_args: argparse.Namespace) -> int:
    """Print cost summary and breakdown."""
    state = load_state()
    cost_data = state.get("cost_breakdown", {})
    running_cost = state.get("running_cost", 0.0)
    iters = state.get("iter", 0)
    print(f"Total Cost: ${running_cost:.4f} across {iters} iterations")
    by_iter = cost_data.get("by_iter", [])
    if by_iter:
        print("Breakdown by iteration:")
        for item in by_iter:
            est_str = " (estimated)" if item.get("is_estimated") else ""
            in_t = item.get("input_tokens") or 0
            out_t = item.get("output_tokens") or 0
            print(f"  Iter {item.get('iter')}: ${_to_float(item.get('cost')):.4f} | "
                  f"model={item.get('model')} | in={in_t} tok, out={out_t} tok{est_str}")
    return EXIT_COMPLETED


def cmd_examples(_args: argparse.Namespace) -> int:
    """List all bundled examples with a one-line description (T7/T9.1)."""
    exdir = DATA_DIR / "examples"
    print("Bundled AgentLoop examples:\n")
    if not exdir.exists():
        print("  (none found)")
        return EXIT_COMPLETED
    for d in sorted(exdir.iterdir()):
        if not d.is_dir():
            continue
        desc = ""
        readme = d / "README.md"
        if readme.exists():
            for line in readme.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    desc = line[:100]
                    break
        if not desc:
            goal = d / "goal.txt"
            if goal.exists():
                desc = goal.read_text().strip().splitlines()[0][:100]
        print(f"  {d.name:<26} {desc}")
    print("\nSeed one with:  agentloop --init --example <name>")
    return EXIT_COMPLETED


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Diagnose common setup issues; exits non-zero with actionable fixes (T9.1)."""
    problems: list[str] = []
    checks: list[tuple[str, bool]] = []

    cmd = resolve_agent_cmd()
    if not cmd:
        problems.append(
            "✗ No agent CLI found. Install one of opencode / kilocode / claude / aider / codex / goose "
            "(e.g. `npm install -g opencode` or `pip install aider-install`), or set AGENT_CMD in .env "
            "to your own command.")
    else:
        binary = cmd.split()[0]
        present = shutil.which(binary) is not None
        checks.append((f"agent CLI: {cmd[:70]}", present))
        if not present:
            problems.append(
                f"✗ Configured agent command {binary!r} is not on PATH. "
                "Fix: install it, or point AGENT_CMD at the correct binary in .env.")

    vcmd = os.environ.get("VERIFY_CMD", "")
    if not vcmd:
        problems.append(
            "✗ No VERIFY_CMD set. Without an oracle the loop trusts the agent's DONE signal. "
            "Fix: run `agentloop --init`, then set VERIFY_CMD=\"bash verify.sh\" in .env.")
    else:
        checks.append((f"verifier: {vcmd}", True))

    if not _args.goal and not GOAL_FILE.exists():
        problems.append(
            "✗ No goal set and no goal.txt found. Fix: run `agentloop --init`, "
            "or pass a goal as the first argument.")

    try:
        SANDBOX.mkdir(parents=True, exist_ok=True)
        probe = SANDBOX / ".agentloop_doctor_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        checks.append((f"sandbox writable ({SANDBOX})", True))
    except Exception as e:
        checks.append(("sandbox writable", False))
        problems.append(f"✗ Sandbox not writable: {e}. Fix: check permissions on {SANDBOX}.")

    if AGENT_MODE == "direct" and not API_KEY:
        problems.append(
            "✗ AGENT_MODE=direct but no AGENTLOOP_API_KEY set. Fix: add AGENTLOOP_API_KEY to .env "
            "(or switch to AGENT_MODE=cli with a real harness).")

    if is_any_telemetry_enabled() and not (_telemetry.enabled or _langfuse.enabled):
        problems.append(
            "✗ Telemetry is configured but the optional dependency is missing. "
            "Fix: pip install 'agentloop[otlp]' and/or 'agentloop[langfuse]'.")

    if USE_DOCKER and shutil.which("docker") is None:
        problems.append("✗ --docker requested but docker not found. Fix: install Docker or drop --docker.")
    if USE_PODMAN and shutil.which("podman") is None:
        problems.append("✗ --podman requested but podman not found. Fix: install Podman or drop --podman.")

    print("AgentLoop doctor — setup check")
    print("=" * 50)
    for label, ok in checks:
        print(f"  {'✔' if ok else '✗'} {label}")
    if problems:
        print("\nProblems found:")
        for p in problems:
            print(f"  {p}")
        print("\nFix the items above, then re-run `agentloop --doctor`.")
        return EXIT_CONFIG
    print("\nAll checks passed. Happy looping!")
    return EXIT_COMPLETED


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="agentloop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Harness-agnostic, self-verifying autonomy wrapper for coding agents.",
        epilog=textwrap.dedent("""\
            examples:
              agentloop "build a JSON linter" --verify "bash verify.sh"
              agentloop --init --example json-linter
              agentloop --run plan.md --workers 4
              agentloop --serve --port 9090
              agentloop --status | --cost | --doctor | --examples
            """))

    g_run = ap.add_argument_group("run options")
    g_run.add_argument("goal", nargs="?", help="task text (writes goal.txt; overrides the file)")
    g_run.add_argument("--verify", help="set VERIFY_CMD — the verification oracle command")
    g_run.add_argument("--harness", help="preset: opencode|kilocode|claude|aider|codex|goose")
    g_run.add_argument("--agent-cmd", help="explicit agent command (overrides --harness)")
    g_run.add_argument("--mode", help="cli (default) | direct")
    g_run.add_argument("--max-iters", type=int, help="max loop iterations")
    g_run.add_argument("--wall", type=int, help="wall-clock limit in seconds")
    g_run.add_argument("--step-delay", type=float, help="delay between iterations (s)")
    g_run.add_argument("--max-cost", type=float, help="max cost in USD (cost cap)")
    g_run.add_argument("--init", action="store_true",
                        help="scaffold goal.txt + verify.sh + .env, then exit")
    g_run.add_argument("--example", type=str, default=None, metavar="NAME",
                        help="seed from a bundled example (see --examples)")
    g_run.add_argument("--dry-run", action="store_true",
                        help="print the resolved configuration and exit (no loop)")

    g_plan = ap.add_argument_group("multi-agent plan options")
    g_plan.add_argument("--run", type=str, default=None, metavar="PLAN.md",
                        help="run tasks from a plan.md file (parallel, DAG-aware)")
    g_plan.add_argument("--workers", type=int, default=0, metavar="N",
                        help="parallel workers for --run (default: min(4, #tasks))")

    g_iso = ap.add_argument_group("container isolation")
    g_iso.add_argument("--docker", action="store_true",
                       help="run agent inside a Docker container (see docs/ISOLATION.md)")
    g_iso.add_argument("--podman", action="store_true",
                       help="run agent inside a Podman container (see docs/ISOLATION.md)")

    g_sub = ap.add_argument_group("subcommands")
    g_sub.add_argument("--status", action="store_true", help="show current run status")
    g_sub.add_argument("--cost", action="store_true", help="show cost breakdown for the latest run")
    g_sub.add_argument("--serve", action="store_true", help="start web monitoring UI")
    g_sub.add_argument("--port", type=int, default=8080, help="HTTP port for --serve (default 8080)")
    g_sub.add_argument("--examples", action="store_true", help="list all bundled examples")
    g_sub.add_argument("--doctor", action="store_true", help="diagnose common setup issues")
    g_sub.add_argument("--version", action="version", version=f"agentloop {__version__}")

    args = ap.parse_args(argv)

    if args.docker:
        os.environ["USE_DOCKER"] = "1"
        read_config()
    if args.podman:
        os.environ["USE_PODMAN"] = "1"
        read_config()

    # Handle subcommands-as-flags
    if args.status:
        return cmd_status(args)
    if args.cost:
        return cmd_cost(args)
    if args.serve:
        return cmd_serve(args)
    if args.examples:
        return cmd_examples(args)
    if args.doctor:
        return cmd_doctor(args)
    if args.run:
        return cmd_run_plan(args)

    if args.init:
        _scaffold(args)
        return EXIT_COMPLETED

    # Auto-create .env with sensible defaults if missing
    if not (ROOT / ".env").exists():
        auto_env = (
            "# Auto-generated by agentloop — edit to customize.\n"
            "AGENT_MODE=cli\n"
            "VERIFY_CMD=\"bash verify.sh\"\n"
        )
        (ROOT / ".env").write_text(auto_env)
        load_env()  # reload so the new values are picked up
        log("created .env with default settings")

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
