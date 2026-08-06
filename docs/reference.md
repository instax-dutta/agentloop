# Reference

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_MODE` | `cli` | `cli` (harness) or `direct` (OpenAI-compatible API) |
| `AGENT_PRESET` | auto | `opencode` \| `kilocode` \| `claude` \| `aider` \| `codex` \| `goose` |
| `AGENT_CMD` | — | Any command; prompt injected via `$AGENTLOOP_PROMPT` |
| `VERIFY_CMD` | — | The verification oracle command |
| `MAX_ITERS` | `50` | Max loop iterations |
| `WALL_CLOCK_SEC` | `21600` | Wall-clock limit (survives resume) |
| `STEP_DELAY` | `3` | Delay between iterations (s) |
| `AGENT_TIMEOUT` | `900` | Per-iteration harness timeout (s) |
| `VERIFY_TIMEOUT` | `120` | Verifier timeout (s) |
| `MAX_COST_USD` | `0` | Cost guard; loop stops with `over-budget` |
| `ESTIMATED_COST_PER_ITER` | `0.10` | CLI-mode estimated cost per iteration |
| `BLOCKED_GOAL_PATTERNS` | — | Hard-block goals matching these substrings |
| `ORACLE_SEAL` | — | Seal for held-out grading (verifier only) |
| `LOG_MAX_MB` | `10` | Rotating log size |
| `LOG_JSON` | `false` | Emit structured JSON log lines |
| `NOTIFY_*` | — | Telegram / Discord / Slack notification credentials |
| `AGENTLOOP_API_KEY` | — | Direct-mode key (legacy `KILO_API_KEY` alias) |
| `AGENTLOOP_MODEL` | `gpt-4o-mini` | Direct-mode model |
| `AGENTLOOP_BASE_URL` | OpenAI | Direct-mode API base URL |
| `USE_DOCKER` / `USE_PODMAN` | `false` | Container isolation |
| `AGENTLOOP_DOCKER_NETWORK` | `none` | Container network policy |
| `AGENTLOOP_DOCKER_IMAGE` | `python:3.12-slim` | Base image |
| `AGENTLOOP_OTEL_ENDPOINT` | — | OTLP trace endpoint (enables telemetry) |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | — | Langfuse telemetry |
| `AGENTLOOP_SANDBOX` / `AGENTLOOP_STATE_FILE` / ... | standard | Per-run path overrides (used by parallel workers) |

## Subcommands

- `agentloop --status` — run status + cost breakdown
- `agentloop --cost` — cost summary for the latest run
- `agentloop --serve [--port N]` — web monitor
- `agentloop --run plan.md [--workers N]` — parallel, DAG-aware plan runner
- `agentloop --examples` — list bundled examples
- `agentloop --doctor` — setup diagnostics
- `agentloop --init [--example NAME]` — scaffold a project
- `agentloop --dry-run` — print resolved config
- `agentloop --version`

## Oracle CLI

```bash
agentloop-oracle record --reference CMD --inputs FILE [--visible N] --out PATH [--seal S]
agentloop-oracle grade --candidate CMD --oracle PATH [--seal S] [--json]
agentloop-oracle gen --reference CMD --n N --out FILE [--seed S]
```

## Exit codes

See [Quickstart](quickstart.md#exit-codes).
