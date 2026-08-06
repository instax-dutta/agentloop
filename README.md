<div align="center">

# AgentLoop — provable correctness for autonomous coding agents.

**A harness-agnostic verify-gate with a held-out oracle, so the agent can't fake 'done'.**

[![CI](https://github.com/instax-dutta/agentloop/actions/workflows/ci.yml/badge.svg)](https://github.com/instax-dutta/agentloop/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/agentloop-cli?color=blue)](https://pypi.org/project/agentloop-cli/)
[![PyPI downloads](https://img.shields.io/pypi/dm/agentloop-cli?color=purple)](https://pypi.org/project/agentloop-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/agentloop-cli?color=green)](https://pypi.org/project/agentloop-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/instax-dutta/agentloop?style=social)](https://github.com/instax-dutta/agentloop/stargazers)

<img src="https://api.star-history.com/svg?repos=instax-dutta/agentloop&type=Date" alt="Star History" width="360" />

</div>

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
```

Free. MIT licensed. Bring your own agent harness (OpenCode, Claude Code, Aider, Codex, Goose) — AgentLoop adds the verify-gate and held-out oracle.

---

## When to use AgentLoop

AgentLoop shines where task correctness can be objectively verified with a held-out oracle or deterministic test suite:

1. **Program Synthesis** — CLI tools, parsers, compilers, validators, data converters.
2. **Behavior-Preserving Refactoring** — Large-scale refactors guarded by golden-file or property-based test capture.
3. **Bug Fixes** — Issues with clear, reproducible failing test cases.

### When NOT to use AgentLoop

- Greenfield UI / web design exploration with no fixed visual contract.
- Exploratory prototyping or open-ended creative brainstorming.
- Anything without a definable, automated "correct" state.

---

## Benchmarks — Proven Lift on SWE-bench-Verified

AgentLoop provides **+16% to +22% lift** over raw agent harnesses on SWE-bench-Verified by preventing false-greens and driving continuous retry until held-out verification passes.

| Harness | Resolve Rate (Raw) | Resolve Rate (+ AgentLoop) | Lift |
|---------|-------------------|--------------------------|------|
| **Claude Code** | 64.0% | **80.0%** | **+16.0%** |
| **OpenCode** | 58.0% | **80.0%** | **+22.0%** |

*See [bench/README.md](bench/README.md) for full reproducible benchmark methodology and raw JSONL logs.*

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

### Run multiple tasks at once — in parallel:

```bash
agentloop --run plan.md            # parallel, min(4, #tasks) workers
agentloop --run plan.md --workers 8
```

Parses any markdown plan — checklists, bullets, headings — and spawns one loop per task **in parallel**, each with its own sandbox (`sandbox/task-N/`) and namespaced state/log files. Add `(after: #N)` or `(depends on: #N)` to a task to express dependencies — AgentLoop builds a DAG, runs ready tasks in parallel, and **skips downstream tasks when a dependency fails**.

> **Parallel-mode verifiers:** each worker's sandbox is `sandbox/task-N/`. Write your `verify.sh` against `$AGENTLOOP_SANDBOX` (set for every worker) so the oracle grades the right sandbox — the bundled examples do this automatically.

### Check your version:

```bash
agentloop --version
# agentloop 0.5.0.dev0
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

Set an estimated cost guard (CLI mode) / hard cap (direct mode with token-counted models) in dollars. If the agent exceeds it, the loop stops with `status=over-budget`:

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

## What makes AgentLoop different

Lots of tools loop a coding agent until it reports "done". Almost none can tell the difference between "the agent said done" and "the work is actually correct".

AgentLoop defines a new category: the **verify-gate wrapper**. Three things, in order of importance:

1. **A held-out verification oracle.** The agent is graded on inputs it has *never seen*, recorded from a trusted reference and sealed against tampering. This is the only mechanism that defeats the SWE-bench false-green problem — an agent that passes the exact test cases you baked in, then fails everything else.
2. **A loop that only stops on proof.** No `DONE` signal is trusted until `VERIFY_CMD` exits 0. Failures are fed back to the agent with the verifier's actual output, so every retry is informed.
3. **Trustworthy plumbing.** Crash-safe atomic state, real token-counted cost tracking, per-iteration git checkpoints, secret-scrubbed environments, and optional container isolation (`--docker` / `--podman`).

If your agent harness already edits code well, the only missing piece is *knowing when it's actually done*. That's the piece AgentLoop supplies.

---

## What's in the box.

| File | What it does |
|------|-------------|
| `agentloop/` | Orchestrator (CLI/direct mode, resume, notifications, web UI, cost dashboard) + `oracle.py` (held-out grading), `cost.py`, `docker.py`, `parallel.py`, `telemetry.py` |
| `verify.sh` / `verify_template.sh` | Example verifier + scaffold template |
| `mock_agent.sh` | Deterministic agent stand-in (for tests) |
| `launch.sh` / `stop.sh` | Linux/Mac launcher scripts |
| `launch.ps1` / `stop.ps1` | Windows PowerShell launchers |
| `examples/` | 10 working verifier samples — see `agentloop --examples` |
| `community-verifiers/` | Community-submitted `verify.sh` patterns — see the [gallery](community-verifiers/README.md) |
| `.pre-commit-config.yaml` | Ruff linting + formatting hooks for contributors |

---

## Real examples. Real verifiers.

The `examples/` directory ships **10 working verifier samples**, each teaching a different oracle pattern:

| Example | Oracle pattern |
|---------|----------------|
| `tax-demo/` | Fixed test cases in bash — a simple, effective oracle |
| `json-linter/` | Temporary test files generated per iteration |
| `regex-engine/` | **Held-out oracle** with adversarial inputs |
| `csv-sorter/` | **Held-out oracle** + property-based testing |
| `markdown-to-html/` | Golden-file comparison |
| `sql-query-rewriter/` | Behavior-equivalence (run both queries, compare results) |
| `python-type-checker/` | Exit-code oracle (`py_compile` / `mypy`) |
| `api-endpoint/` | Integration oracle over HTTP |
| `git-history-rewriter/` | Fixture-based oracle with real git repos |
| `refactor-regression/` | **Held-out oracle** — gen + record + grade workflow (the moat) |

Each has a `goal.txt` (the task) and `verify.sh` (the oracle). Run `./verify.sh` to see how the oracle works without the loop. Browse the full gallery — with runtime/cost estimates and how to pick a pattern — in [docs/EXAMPLES.md](docs/EXAMPLES.md).

Built a verifier worth sharing? Add it to the [community-verifiers gallery](community-verifiers/README.md) — copy-paste-able `verify.sh` patterns with a merge checklist, so your oracle pattern becomes a template for everyone else.

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

- The wrapped agent runs with `cwd=sandbox`. For hard isolation, use `--docker` or `--podman` (see [ISOLATION.md](docs/ISOLATION.md)).
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

**AgentLoop is 0.5.0-dev. MIT licensed. Zero runtime dependencies. One purpose: make your agent actually finish.**

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
```

[Report an issue](https://github.com/instax-dutta/agentloop/issues) · [Contributing guide](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
