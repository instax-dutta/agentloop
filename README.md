# AgentLoop

Run coding agents in a verification loop until the task actually passes your checks.

AgentLoop re-invokes your chosen agent, feeds failures back into the next iteration, and stops only when a human-authored verifier says the work is correct.

- Works with multiple agent harnesses
- Retries until verification passes
- Resumes after crashes
- Supports held-out verification
- Supports cost caps and notifications

```text
goal -> agent edits -> verify fails -> failure fed back -> agent retries -> verify passes
```

## Why this exists

Coding agents often stop halfway or pass only the obvious cases. A naive loop that checks whether the agent said "DONE" fails in two common ways:

1. **Partial completion.** The agent quits mid-task; the loop thinks it won.
2. **Overfitting.** If the checks are visible to the agent, it can pass without being generally correct.

AgentLoop fixes both by separating the agent from the verifier:

- the agent makes changes
- the verifier decides whether the work is actually correct
- AgentLoop keeps retrying until the verifier passes

## Why people use it

AgentLoop is useful when "looks right" is not enough and you need proven correctness.

- Works with OpenCode, Kilo Code, Claude Code, Aider, Codex, and Goose
- Keeps a run going even if the process crashes
- Lets you use human-authored or held-out checks
- Tracks cost and can stop before runaway bills
- Sends terminal-state notifications

## Quick start

```bash
git clone <this> agentloop && cd agentloop
python3 -m pip install -e .
cp .env.example .env
chmod +x launch.sh stop.sh verify.sh mock_agent.sh oracle.py
```

You need **OpenCode installed** (`npm i -g opencode` or your package manager) and a free model configured in it. No API key is required by AgentLoop itself.

### One-liner

```bash
agentloop "build a JSON linter" --verify "bash verify.sh"
agentloop --dry-run --harness opencode --verify "bash verify.sh"
agentloop --init
agentloop --version
agentloop --status
agentloop --serve
```

Or the file-based flow:

1. Put the task in `goal.txt`.
2. Write a verification oracle — a script that exits 0 only when the work is correct.
3. Run `./launch.sh`, watch `tail -f agentloop.log`, stop with `./stop.sh`.

## The verification oracle

The agent's own tests are not trusted: it can validate "it runs" without noticing wrong numbers. Instead, a separate human-authored check is run by the harness on each iteration:

- Exit 0 → accepted, loop ends, `agentloop.summary.txt` is written, notifications fire.
- Non-zero → the failure output is injected back into the next prompt and the agent must keep working.

### Sealed / held-out oracle

A plain check can still be gamed if the author leaks the exact cases to the agent. To stop that, keep a case file outside the sandbox and split it into visible and held-out inputs:

```bash
python oracle.py gen --reference "python ref.py" --n 200 --out cases.txt --seed 42
python oracle.py record \
  --reference "python ref.py" --inputs cases.txt --visible 3 \
  --out .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
python oracle.py grade \
  --candidate "python sandbox/solution.py" \
  --oracle .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
```

The candidate only passes if it is correct on inputs it has never seen. A wrong `--seal` makes grading report `TAMPERED`.

## Crash-safe resume + summary

AgentLoop writes `agentloop.state.json` every iteration. If the process or machine dies, run it again with the same goal and it resumes from the last iteration instead of re-planning.

```text
resuming from iter 2 (cost so far: $0.10)
```

When the run ends it writes `agentloop.summary.txt` and fires notifications.

## Hard per-run cost cap

Prevent runaway API bills with `MAX_COST_USD`:

```bash
MAX_COST_USD=5 agentloop "my task" --verify "bash verify.sh"
```

The loop tracks running cost in `agentloop.state.json` and stops with `status=over-budget` when the cap is exceeded. In CLI mode, set `ESTIMATED_COST_PER_ITER` to approximate cost. In direct mode, actual token counts are used when available.

## Hands-off notifications

Send terminal-state summaries via generic command, Telegram, Discord, or Slack:

```bash
NOTIFY_CMD='curl -s -X POST https://hooks.example.com -d "{kind}: {msg}"'
NOTIFY_TELEGRAM_BOT_TOKEN=123456:ABC-DEF
NOTIFY_TELEGRAM_CHAT_ID=-1001234567890
NOTIFY_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
NOTIFY_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

`{kind}` and `{msg}` are substituted into the generic command. Native adapters use the REST API directly.

## Run monitoring

```bash
agentloop --status
agentloop --serve
agentloop --serve --port 9090
```

## Harnesses (`.env`)

```bash
AGENT_MODE=cli
AGENT_PRESET=opencode
VERIFY_CMD="bash verify.sh"
# NOTIFY_CMD='...'
# TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
# MAX_COST_USD=5
```

If `AGENT_PRESET` is empty, AgentLoop auto-detects an installed CLI with version checks. Or set `AGENT_CMD` to any command; the prompt is injected via `$AGENTLOOP_PROMPT`:

```bash
AGENT_CMD='opencode run "$AGENTLOOP_PROMPT" --auto'
```

| Preset    | Command |
|-----------|---------|
| opencode  | `opencode run "$AGENTLOOP_PROMPT" --auto` |
| kilocode  | `kilocode run "$AGENTLOOP_PROMPT"` |
| claude    | `claude -p "$AGENTLOOP_PROMPT" --dangerously-skip-permissions` |
| aider     | `aider --message "$AGENTLOOP_PROMPT" --yes` |
| codex     | `codex exec "$AGENTLOOP_PROMPT"` |
| goose     | `goose run "$AGENTLOOP_PROMPT"` |

## Direct mode (legacy / offline)

If you have no harness installed, `AGENT_MODE=direct` calls an OpenAI-compatible API directly. Set `KILO_API_KEY`, `KILO_BASE_URL`, and `KILO_MODEL` in `.env`.

## Examples gallery

| Example | Description | Verifier Type |
|---------|-------------|---------------|
| `tax-demo/` | US tax calculator | Fixed cases in bash |
| `json-linter/` | JSON syntax validator | Temporary test files |
| `refactor-regression/` | Refactor with identical output | Held-out oracle (gen + record + grade) |

Each example has a `goal.txt` and `verify.sh`.

## Tests

```bash
python3 test_oracle.py
python3 test_loop.py
```

Both run deterministically without any model.

## Pre-commit hooks

```bash
pip install -e '.[dev]'
pre-commit install
```

## Limitations

- The wrapped agent runs with `cwd=sandbox`; AgentLoop relies on the harness's own permission model. For hard isolation, run inside a container.
- Without `VERIFY_CMD`, the loop falls back to a full-line `DONE` / `BLOCKED` signal from the agent; a verifier is strongly recommended.
- Each CLI iteration is a fresh agent invocation; continuity is maintained by feeding goal + last failure back, not by an in-agent session.
- The held-out case file should live outside the sandbox; the seal is a tamper signal, not absolute security.
- API keys and `ORACLE_SEAL` are stripped from the agent environment; the seal is passed only to `VERIFY_CMD`.

## Files

- `agentloop.py` — orchestrator (CLI + direct modes, resume, notify)
- `oracle.py` — verification oracle + sealed / held-out record / grade + input generation
- `verify.sh` / `verify_template.sh` — example oracle + scaffold template
- `mock_agent.sh` — deterministic stand-in for a real agent CLI
- `launch.sh` / `stop.sh` — Linux / Mac launcher scripts
- `launch.ps1` / `stop.ps1` — Windows launcher scripts
- `goal.txt` / `.env.example` / `CHANGELOG.md` / `CONTRIBUTING.md`
- `.pre-commit-config.yaml` — ruff linting hooks
- `examples/` — working verifier samples

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
