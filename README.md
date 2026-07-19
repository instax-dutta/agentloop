# AgentLoop

**A harness-agnostic, self-verifying autonomy wrapper. The verification oracle is the product.**

AgentLoop is *not* a coding agent and *not* a BYOK harness. It drives the coding
agent you already use — **OpenCode by default** (free models, no key from us),
also Kilo Code / Claude Code / Aider / Codex / Goose — in a loop until the goal is
*actually met and proven correct*:

```
   goal + feedback ──► your agent edits the sandbox ──► verification oracle
          ▲                                                   │
          └────────────── (fail) ◄───────────────────────────┘
                         (pass) ──► DONE  (and a sealed oracle agrees)
```

The harness supplies the model and auth. AgentLoop only adds three things
people keep rebuilding by hand:

* **continuity** — it loops until the goal is really done (no "please clarify"),
* **the verification oracle** — a correctness gate, not "it runs and prints",
* **safety** — your key is never exposed to the wrapped agent; work is
  git-checkpointed and, if the process dies, **resumed** from where it stopped.

## Why this exists (read this before you write a 20-line bash loop)

Coding agents are famous for **stopping halfway** and claiming they're done
(OpenCode issue #24685 and many duplicates; the "stopped halfway" essays). A
naive loop — *"run the agent, check if it said DONE"* — fails two ways:

1. **Partial completion.** The agent quits mid-task; your loop thinks it won.
2. **Overfitting.** If you bake the exact test cases into the check, the agent
   can pass without being *generally* correct (the SWE-bench false-green bug).

AgentLoop fixes both: it gates on a **human-authored oracle** the agent can't
edit, and the oracle can run against **held-out inputs the agent never saw**
(see below). It also survives a crash: rerun it and it resumes the same goal.

## Install / quick start

```bash
git clone <this> agentloop && cd agentloop
python3 -m pip install -e .
# optional: direct-mode OpenAI-compatible API client
# python3 -m pip install -e '.[direct]'
# optional: developer tooling (ruff, pre-commit)
# python3 -m pip install -e '.[dev]'
cp .env.example .env
chmod +x launch.sh stop.sh verify.sh mock_agent.sh oracle.py
```

You need **OpenCode installed** (`npm i -g opencode` or your package manager) and
a free model configured in it. No API key is required by AgentLoop itself.

### One-liner

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
agentloop --dry-run --harness opencode --verify "bash verify.sh"   # show config, do nothing
agentloop --init                                                    # scaffold goal.txt + verify.sh + .env
agentloop --version
agentloop --status                                                   # show current run status
agentloop --serve                                                    # start web monitoring UI
```

Or the file-based flow:

1. Put the task in `goal.txt`.
2. Write a **verification oracle** — a script that exits 0 only when the work is
   correct. The agent never edits this, so it can't fake it.
3. `./launch.sh` (or `agentloop`), `tail -f agentloop.log`, `./stop.sh`.

### Windows (PowerShell)

```powershell
.\launch.ps1       # start the loop (background job)
.\stop.ps1         # stop gracefully
```

### Multi-agent: run a plan

```bash
agentloop --run plan.md
```

Parses a markdown file with `- [ ] task` items and spawns one agent loop per task.

## The verification oracle (the important part)

The agent's *own* tests are not trusted: it can validate "it runs" without
noticing wrong numbers. Instead, a separate, human-authored check is run by the
harness on each iteration:

* Exit 0 → accepted, loop ends, `agentloop.summary.txt` written, `NOTIFY_CMD` fired.
* Non-zero → the failure output is injected back into the next prompt and the
  agent **must keep working**.

### Sealed / held-out oracle (defeats overfitting)

A plain check can still be gamed if the author leaks the exact cases to the
agent. To stop that, keep a **case file outside the sandbox** and split it into
*visible* (may be shown to the agent) and *held-out* (the agent never sees them):

```bash
# 1) auto-generate fresh test inputs from a reference program
python oracle.py gen --reference "python ref.py" --n 200 --out cases.txt --seed 42

# 2) record a trusted reference's behaviour (keep oracle.json OUTSIDE the sandbox)
python oracle.py record \
  --reference "python ref.py" --inputs cases.txt --visible 3 \
  --out .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"

# 3) the verifier grades the candidate against ALL inputs (visible + held-out)
python oracle.py grade \
  --candidate "python sandbox/solution.py" \
  --oracle .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
```

The candidate only **PASSES if it is correct on the inputs it has never seen**.
A wrong `--seal` makes grading report `TAMPERED`. See `verify_template.sh` for a
drop-in template. This is the feature that makes AgentLoop worth using over a
hand-rolled loop — it's the same idea as dedicated "verification oracle"
projects, packaged for the autonomous-coding loop.

## Crash-safe resume + summary

AgentLoop writes `agentloop.state.json` every iteration. If the process (or your
machine) dies, just run it again with the **same goal** and it resumes from the
last iteration instead of re-planning:

```
resuming from iter 2 (cost so far: $0.10)
```

When the run ends it writes `agentloop.summary.txt` (`status=... iters=... elapsed=... goal=...`) and fires notifications.

## Hard per-run cost cap

Prevent runaway API bills with `MAX_COST_USD`:

```bash
MAX_COST_USD=5 agentloop "my task" --verify "bash verify.sh"
```

The loop tracks running cost in `agentloop.state.json` and stops with
`status=over-budget` when the cap is exceeded. In CLI mode, set
`ESTIMATED_COST_PER_ITER` (default $0.10) to approximate cost. In direct mode,
actual token counts from the API response are used when available.

## Hands-off notifications

Send terminal-state summaries via generic command, Telegram, Discord, or Slack:

```bash
# Generic: any shell command
NOTIFY_CMD='curl -s -X POST https://hooks.example.com -d "{kind}: {msg}"'

# Telegram (set both)
NOTIFY_TELEGRAM_BOT_TOKEN=123456:ABC-DEF
NOTIFY_TELEGRAM_CHAT_ID=-1001234567890

# Discord (webhook URL)
NOTIFY_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Slack (webhook URL)
NOTIFY_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

`{kind}` (completed/blocked/stopped/timeout/over-budget) and `{msg}` are
substituted into the generic command. Native adapters use the REST API directly
with no extra dependencies.

## Run monitoring

```bash
agentloop --status      # terminal status display
agentloop --serve       # web UI at http://localhost:8080 (auto-refresh 5s)
agentloop --serve --port 9090   # custom port
```

## Harnesses (`.env`)

```bash
AGENT_MODE=cli
AGENT_PRESET=opencode     # primary target; ships free models, no key needed
VERIFY_CMD="bash verify.sh"
# NOTIFY_CMD='...'                              # optional
# TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...   # optional
# MAX_COST_USD=5                                # optional cost cap
```

If `AGENT_PRESET` is empty, AgentLoop auto-detects an installed CLI (with
version checks). Or set `AGENT_CMD` to any command; the prompt is injected via
`$AGENTLOOP_PROMPT`:

```bash
AGENT_CMD='opencode run "$AGENTLOOP_PROMPT" --auto'
```

| Preset    | Command                                              |
|-----------|------------------------------------------------------|
| opencode  | `opencode run "$AGENTLOOP_PROMPT" --auto`            |
| kilocode  | `kilocode run "$AGENTLOOP_PROMPT"`                   |
| claude    | `claude -p "$AGENTLOOP_PROMPT" --dangerously-skip-permissions` |
| aider     | `aider --message "$AGENTLOOP_PROMPT" --yes`          |
| codex     | `codex exec "$AGENTLOOP_PROMPT"`                     |
| goose     | `goose run "$AGENTLOOP_PROMPT"`                      |

**Hidden strength:** because AgentLoop re-invokes the harness *every iteration*,
a harness that "stops halfway" (the OpenCode bug above) just becomes one failed
iteration — the loop absorbs it and keeps going.

## Direct mode (legacy / offline)

If you have no harness installed, `AGENT_MODE=direct` calls an OpenAI-compatible
API directly (one continuous reasoning thread, same tools + oracle). Set
`KILO_API_KEY` / `KILO_BASE_URL` / `KILO_MODEL` in `.env`.

## Log rotation

Logs are automatically rotated at `LOG_MAX_MB` (default 10 MB) with 3 backup
files. Set in `.env`:

```
LOG_MAX_MB=25
```

## Input auto-generation

`oracle.py gen` automatically produces fresh test inputs from a reference
program using multiple generative strategies (random integers, floats, strings,
structured data):

```bash
oracle.py gen --reference "python ref.py" --n 200 --out cases.txt --seed 42
oracle.py record --reference "python ref.py" --inputs cases.txt --visible 10 --out oracle.json
oracle.py grade --candidate "python cand.py" --oracle oracle.json
```

## Examples gallery

The `examples/` directory contains three working verifier samples:

| Example | Description | Verifier Type |
|---------|-------------|---------------|
| `tax-demo/` | US tax calculator | Fixed cases in bash |
| `json-linter/` | JSON syntax validator | Temporary test files |
| `refactor-regression/` | Refactor with identical output | Held-out oracle (gen + record + grade) |

Each example has a `goal.txt` (the task) and `verify.sh` (the oracle).

## Tests

```bash
python3 test_oracle.py   # the verification gate + held-out oracle (no LLM)
python3 test_loop.py     # full loop using mock_agent.sh + cost cap + status + more
```

Both run deterministically without any model.

## Pre-commit hooks

```bash
pip install -e '.[dev]'
pre-commit install
```

## Files

* `agentloop.py` — orchestrator (cli + direct modes, resume, notify, CLI)
* `oracle.py`    — verification oracle + sealed/held-out record/grade + input gen
* `verify.sh` / `verify_template.sh` — example oracle + scaffold template
* `mock_agent.sh`— deterministic stand-in for a real agent CLI (for tests)
* `launch.sh` / `stop.sh` — Linux/Mac launcher scripts
* `launch.ps1` / `stop.ps1` — Windows launcher scripts
* `goal.txt` / `.env.example` / `CHANGELOG.md` / `CONTRIBUTING.md`
* `.pre-commit-config.yaml` — ruff linting hooks
* `examples/` — 3 working verifier samples

## Exit codes

| Status | Code |
|--------|------|
| completed | 0 |
| blocked | 1 |
| config / missing agent | 2 |
| timeout (wall clock) | 3 |
| exhausted (max iters) | 4 |
| over-budget (cost cap) | 5 |
| stopped (STOP / signal) | 130 |

## Limitations

* The wrapped agent runs with `cwd=sandbox`; AgentLoop relies on the harness's
  own permission model. For hard isolation, run inside a container (see ISSUES.md).
* Without a `VERIFY_CMD`, the loop falls back to a full-line `DONE`/`BLOCKED`
  signal from the agent — a verifier is strongly recommended.
* Each CLI iteration is a fresh agent invocation; "continuity" is maintained by
  AgentLoop feeding goal + last failure back, not by an in-agent session.
* The held-out case file should live outside the sandbox; the seal is a
  tamper *signal*, not absolute security — keep secrets out of the agent's reach.
* API keys and `ORACLE_SEAL` are stripped from the agent environment; the seal
  is passed only to `VERIFY_CMD`. Never put secrets in the sandbox.
