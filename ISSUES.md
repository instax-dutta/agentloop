# AgentLoop — Issues Tracking

> **Status:** Issues #1, #3–#10 closed as implemented in [v0.3.0](CHANGELOG.md). Only #2 remains open.

---

## ✅ Closed: Implemented in v0.2.0 (Phase A production hardening)

- Secret scrubbing: API keys / tokens never reach the agent; `ORACLE_SEAL` only reaches `VERIFY_CMD`
- `.env` untracked; `.env.example` + gitignore; installable package (`pyproject.toml`, `agentloop` CLI)
- Direct-mode reflection control flow fixed; wall-clock uses absolute `started_at` across resume
- Full-line `DONE`/`BLOCKED` matching; atomic state/summary writes; SIGTERM/SIGINT → STOP
- Sandbox auto `git init` for checkpoints; graceful `stop.sh`; structured exit codes
- CI workflow (Linux, Python 3.10/3.12/3.13); LICENSE; CONTRIBUTING; `--version`

---

## ✅ Closed: Implemented in v0.3.0

### #1 — Hard per-run cost cap
`MAX_COST_USD` env var, tracks running cost in `agentloop.state.json`, aborts with `over-budget` status.

### #3 — Native notify integrations
First-class Telegram, Discord, and Slack adapters via env vars (`NOTIFY_TELEGRAM_BOT_TOKEN`, `NOTIFY_DISCORD_WEBHOOK_URL`, `NOTIFY_SLACK_WEBHOOK_URL`).

### #4 — Held-out oracle UX: auto-generate fresh inputs
`oracle.py gen` command with random integer, float, string, and structured data strategies.

### #5 — More harness presets + smarter auto-detect
Version-check auto-detect, `goose` preset, Windows-friendly paths.

### #6 — Run monitoring: `agentloop status` / web view
`agentloop status` (CLI summary) + `agentloop serve` (web UI at `http://localhost:8080`).

### #7 — Parallel / multi-agent orchestration
`agentloop run plan.md` parses plan files and spawns sub-loops per task.

### #8 — CI + Windows support
`launch.ps1` / `stop.ps1`, GitHub Actions CI for Linux + Python 3.10/3.12/3.13.

### #9 — Docs: CONTRIBUTING + examples gallery
`CONTRIBUTING.md`, `examples/` with tax-demo, JSON linter, and refactor-regression.

### #10 — Real-harness integration test
Gated nightly CI job running AgentLoop against real OpenCode.

---

## 🔴 Still Open

### #2. Container / hard-isolation sandbox mode
The wrapped agent runs with `cwd=sandbox` but relies on the harness's own
permission model. Add a `--docker` mode that runs the agent CLI inside an
ephemeral, network-egress-limited container with a scoped, credential-free
token, so untrusted agents can't touch the host.

**Acceptance:** `agentloop --docker "goal" --verify ...` spins up a container, mounts
only `sandbox/`, and tears it down on exit.
