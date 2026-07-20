<div align="center">

# Stop paying for agents that never finish.

**AgentLoop makes your coding agent actually complete tasks correctly — or it keeps going.**

[![CI](https://github.com/instax-dutta/agentloop/actions/workflows/ci.yml/badge.svg)](https://github.com/instax-dutta/agentloop/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/agentloop-cli?color=blue)](https://pypi.org/project/agentloop-cli/)
[![PyPI downloads](https://img.shields.io/pypi/dm/agentloop-cli?color=purple)](https://pypi.org/project/agentloop-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/agentloop-cli?color=green)](https://pypi.org/project/agentloop-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

</div>

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
```

Free. MIT licensed. Free models. No API key needed. Works with OpenCode, Claude Code, Aider, Goose, and more.

---

## You already know the pain.

Coding agents are famous for **stopping halfway** and claiming they're done.

OpenCode issue [#24685](https://github.com/instax-dutta/agentloop/issues). The "stopped halfway" essays. You've been there:

- The agent writes 80% of the code, then quits. Your loop thinks it won.
- You bake test cases into your check script — now the agent overfits, passing those exact cases but failing on everything else. (This is the [SWE-bench false-green bug](https://arxiv.org/abs/2410.14816), and it's real.)
- Your API bill keeps climbing while nothing ships.

You've probably thought: *"I'll just write a 20-line bash loop."*

**That doesn't work either.** A naive loop can't tell the difference between "the agent said DONE" and "the agent *actually* solved the problem." You need a **verification oracle** — a correctness gate the agent can't fake, edit, or overfit to.

That's what AgentLoop is.

---

## The verification oracle is the product.

AgentLoop is **not** a coding agent and **not** another BYOK wrapper. It's a thin, harness-agnostic layer that wraps the agent you already use:

```
   goal + feedback ──► your agent edits the sandbox ──► verification oracle
          ▲                                                   │
          └────────────── (fail) ◄───────────────────────────┘
                         (pass) ──► DONE  (and a sealed oracle agrees)
```

Three things it adds that people keep rebuilding by hand:

- **Continuity** — loops until the goal is proven correct, not "please clarify"
- **The verification oracle** — a correctness gate, not "it runs and prints"
- **Safety** — your API key never reaches the agent; work is git-checkpointed and crash-resumable

> **"Wait — a naive loop can't tell if the work is correct."**  
> *Correct. That's why AgentLoop exists.*

### The held-out oracle (your moat against overfitting)

A plain verifier can still be gamed if the agent reverse-engineers the test cases. AgentLoop's **sealed, held-out grading** defeats that:

```bash
# 1) Auto-generate fresh test inputs from a reference program
python oracle.py gen --reference "python ref.py" --n 200 --out cases.txt --seed 42

# 2) Record the reference's behavior — split into visible + held-out (sealed)
python oracle.py record \
  --reference "python ref.py" --inputs cases.txt --visible 3 \
  --out .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"

# 3) The verifier grades the candidate against ALL inputs
#    The candidate only PASSES if it's correct on inputs it has NEVER seen
python oracle.py grade \
  --candidate "python sandbox/solution.py" \
  --oracle .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
```

A wrong `--seal` makes grading report **TAMPERED**. The held-out file lives outside the sandbox — the agent can't read it, can't overfit to it. This is the feature that makes AgentLoop worth using over a hand-rolled loop.

---

## Install in 5 seconds.

**From PyPI (recommended):**

```bash
pip install agentloop-cli
agentloop --init
./launch.sh
```

**Or from source:**

```bash
git clone https://github.com/instax-dutta/agentloop.git && cd agentloop
pip install -e "."
agentloop --init
./launch.sh
```

That's it. No API key. No `.env` to copy. No config to edit.

**`agentloop --init`** creates everything you need:
- `goal.txt` — a hello-world task
- `verify.sh` — a working verifier, ready to run
- `.env` — zero-config defaults

Need Windows?

```powershell
.\launch.ps1       # start the loop (background job)
.\stop.ps1         # stop gracefully
```

### Try a real example instead:

```bash
agentloop --init --example tax-demo
# Seeds: goal.txt + verify.sh from the tax-demo example
```

Or jump straight in:

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
```

### Preview your setup before running:

```bash
agentloop --dry-run
# Shows: mode, agent command, verify command, goal, limits, version — no loop starts
```

### Run multiple tasks at once:

```bash
agentloop --run plan.md
```

Parses any markdown plan — checklists, bullets, headings — and spawns one loop per task.

### Check your version:

```bash
agentloop --version
# agentloop 0.3.0
```

---

## It survives crashes.

Your laptop dies mid-run. Your SSH session drops. Your CI runner gets recycled.

**AgentLoop resumes exactly where it stopped.**

```bash
# Same command, same goal:
agentloop --verify "bash verify.sh"
# Output:
# resuming from iter 2 (cost so far: $0.10)
```

Every iteration is written atomically to `agentloop.state.json`. A crash leaves zero torn state. The wall clock tracks from the original start — not the resume time — so timeouts are fair.

---

## Don't let a runaway API bill surprise you.

Set a hard cost cap in dollars. If the agent exceeds it, the loop stops with `status=over-budget`:

```bash
MAX_COST_USD=5 agentloop "my task" --verify "bash verify.sh"
```

Tracks running cost in `agentloop.state.json`. In CLI mode, set `ESTIMATED_COST_PER_ITER` ($0.10 default). In direct mode, actual token counts are used automatically.

### Logs rotate automatically.

Set `LOG_MAX_MB` in `.env` (default 10 MB) with 3 backup files via Python's `RotatingFileHandler`. No more gigabyte log files.

---

## Know exactly what's happening.

```bash
agentloop --status       # terminal display: status, iters, elapsed, cost, PID
agentloop --serve        # web UI at http://localhost:8080 (auto-refresh 5s)
agentloop --serve --port 9090   # custom port
```

---

## Get notified when it finishes.

Send terminal-state summaries wherever you work:

```bash
# Telegram
NOTIFY_TELEGRAM_BOT_TOKEN=123456:ABC-DEF
NOTIFY_TELEGRAM_CHAT_ID=-1001234567890

# Discord (webhook URL)
NOTIFY_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Slack (webhook URL)
NOTIFY_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Or any shell command
NOTIFY_CMD='curl -s -X POST https://hooks.example.com -d "{kind}: {msg}"'
```

Supports: `completed`, `blocked`, `stopped`, `timeout`, `over-budget` — each routed through your preferred channel.

---

## Works with whatever agent you use.

| Preset    | Command                                              |    
|-----------|------------------------------------------------------|
| opencode  | `opencode run "$AGENTLOOP_PROMPT" --auto`            |
| kilocode  | `kilocode run "$AGENTLOOP_PROMPT"`                   |
| claude    | `claude -p "$AGENTLOOP_PROMPT" --dangerously-skip-permissions` |
| aider     | `aider --message "$AGENTLOOP_PROMPT" --yes`          |
| codex     | `codex exec "$AGENTLOOP_PROMPT"`                     |
| goose     | `goose run "$AGENTLOOP_PROMPT"`                      |

No preset matching yours? Set `AGENT_CMD` to any command. The prompt is injected via `$AGENTLOOP_PROMPT`.

```bash
AGENT_CMD='my-agent run "$AGENTLOOP_PROMPT"'
```

If no preset is set, AgentLoop **auto-detects** an installed CLI with a version check — and warns you if it finds a broken binary.

**Hidden strength:** Because AgentLoop re-invokes the harness *every iteration*, a harness that "stops halfway" just becomes one failed iteration. The loop absorbs it and keeps going.

---

## AgentLoop vs GNHF

Both tools loop coding agents until a task is done, but they solve different problems.

| Feature | AgentLoop | [GNHF](https://github.com/kunchenguid/gnhf) "Good Night, Have Fun" |
|---------|:--------:|:----:|
| **Verification oracle** | ✅ Independent, unskippable gate | ❌ No oracle — trusts agent's "done" signal |
| **Held-out grading** (anti-overfitting) | ✅ Sealed, tamper-evident | ❌ |
| **Crash-safe resume** | ✅ Atomic state, survives reboot | ❌ Fresh start on crash |
| **Hard cost cap** ($ limit) | ✅ MAX_COST_USD | ❌ Max iterations only |
| **Notifications** (Telegram/Discord/Slack) | ✅ Built-in | ❌ |
| **Web monitoring** | ✅ Built-in HTTP server | ❌ |
| **Environment scrubbing** (API key safety) | ✅ Automated | ❌ |
| **Install** | `pip install agentloop-cli` | `brew` or clone + `npm install` |
| **Dependencies** | **Zero** — pure Python, no npm | Node.js + npm |
| **Lines of code** | ~2,000 | ~10,000+ |
| **License** | MIT | MIT |

**The difference:** GNHF is an *orchestrator* that keeps agents running through the night. AgentLoop is a *correctness enforcer* that keeps agents running *until the work is proven correct*. The held-out oracle — which GNHF lacks — is what prevents your agent from claiming victory on broken code.

---

## What's in the box.

| File | What it does |
|------|-------------|
| `agentloop.py` | Orchestrator — CLI mode, direct mode, resume, notifications, web UI |
| `oracle.py` | Verification oracle — sealed held-out grading, input generation |
| `verify.sh` / `verify_template.sh` | Example verifier + scaffold template |
| `mock_agent.sh` | Deterministic agent stand-in (for tests) |
| `launch.sh` / `stop.sh` | Linux/Mac launcher scripts |
| `launch.ps1` / `stop.ps1` | Windows PowerShell launchers |
| `examples/` | 3 working verifier samples — tax-demo, JSON linter, refactor-regression |
| `.pre-commit-config.yaml` | Ruff linting + formatting hooks for contributors |

---

## Real examples. Real verifiers.

The `examples/` directory shows three different approaches:

| Example | What it teaches |
|---------|----------------|
| `tax-demo/` | Fixed test cases in bash — a simple, effective oracle |
| `json-linter/` | Temporary test files generated per iteration |
| `refactor-regression/` | **Held-out oracle** — gen + record + grade workflow (the moat) |

Each has a `goal.txt` (the task) and `verify.sh` (the oracle). Run `./verify.sh` to see how the oracle works without the loop.

---

## Exit codes (for CI / scripting).

| Status | Code | Meaning |
|--------|------|---------|
| completed | 0 | Goal met, verification passed |
| blocked | 1 | Agent gave up |
| config / missing agent | 2 | Something isn't set up |
| timeout | 3 | Wall-clock limit hit |
| exhausted | 4 | Max iterations reached |
| over-budget | 5 | Cost cap exceeded |
| stopped | 130 | SIGTERM/SIGINT / STOP file |

---

## The fine print.

- The wrapped agent runs with `cwd=sandbox`. For hard isolation, use a container (see [ISSUES.md](ISSUES.md#2)).
- Without `VERIFY_CMD`, the loop falls back on a `DONE`/`BLOCKED` signal from the agent — use a real verifier.
- Each CLI iteration is a fresh agent invocation. Continuity is maintained by feeding the goal + last failure back.
- Keep the held-out case file outside the sandbox. The seal is a tamper *signal*, not absolute security.
- API keys and `ORACLE_SEAL` are stripped from the agent environment. Never put secrets inside the sandbox.

---

## Tests (deterministic, no LLM required)

```bash
python3 test_oracle.py   # verification gate + held-out oracle
python3 test_loop.py     # full loop with mock agent + cost cap + status
```

Both pass on every commit. CI runs them on Linux (Python 3.10/3.12/3.13).

### Pre-commit hooks (for contributors)

```bash
pip install -e '.[dev]'
pre-commit install
```

---

## End-to-End Testing (verified from PyPI)

All features work from a fresh `pip install agentloop-cli` in a clean virtual environment.

| Test | What it proves | Status |
|------|---------------|:------:|
| `agentloop --version` | CLI is installed and executable | ✅ |
| `agentloop --init` | Scaffolds `goal.txt`, `verify.sh`, `.env` | ✅ |
| `agentloop --dry-run` | Configuration resolves correctly | ✅ |
| `--example tax-demo` | Seeds a real tax-calculator project | ✅ |
| `--example json-linter` | Seeds a JSON linter project | ✅ |
| `--example refactor-regression` | Seeds a held-out oracle demo | ✅ |
| `oracle gen` — generates 20 test inputs | Genuine edge cases included | ✅ |
| `oracle record` — splits 3 visible / 17 held-out | Cryptographic seal prevents tampering | ✅ |
| `oracle grade` — correct solution | **PASS** — 20/20 score 1.00 | ✅ |
| `oracle grade` — broken solution | **FAIL** — 1/20 score 0.05 | ✅ |
| `oracle grade` — wrong seal | **TAMPERED** detected | ✅ |
| `test_oracle.py` (CI) | Oracle gate + held-out grading + env scrubbing | ✅ every commit |
| `test_loop.py` (CI) | Full mock-agent loop + resume + cost cap | ✅ every commit |

**Results:** All **13 E2E checks pass**. The held-out oracle correctly passes correct code (score 1.00), fails broken code (score 0.05), and detects tampering when the seal is wrong.

```bash
# Run the E2E suite yourself:
pip install agentloop-cli
agentloop --init --example tax-demo
agentloop --dry-run
agentloop-oracle gen --reference 'python3 -c "import sys; print(int(sys.stdin.read().strip()) * 2)"' --n 20 --out cases.txt --seed 42
agentloop-oracle record --reference 'python3 -c "import sys; print(int(sys.stdin.read().strip()) * 2)"' --inputs cases.txt --visible 3 --out oracle.json --seal test-seal
agentloop-oracle grade --candidate 'python3 -c "import sys; print(int(sys.stdin.read().strip()) * 2)"' --oracle oracle.json --seal test-seal
```

---

**AgentLoop is 0.4.0. MIT licensed. One file. One purpose: make your agent actually finish.**

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
```

[Report an issue](https://github.com/instax-dutta/agentloop/issues) · [Contributing guide](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
