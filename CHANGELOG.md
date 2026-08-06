# Changelog

All notable changes to AgentLoop are documented here.

## [0.5.0-dev] — 2026-08-06

### Added

- **True parallel multi-agent fan-out** — `agentloop --run plan.md` now runs
  tasks in parallel with per-task sandboxes (`sandbox/task-N/`) and namespaced
  state/log/pid files. `--workers N` controls concurrency. DAG dependencies
  via `(after: #N)` / `(depends on: #N)` (comma-separated lists supported);
  downstream tasks are **skipped** when a dependency fails. (#7)

- **Optional telemetry** — `agentloop/telemetry.py` with an OpenTelemetry
  exporter (extras `[otlp]`) and a Langfuse exporter (extras `[langfuse]`).
  Both are zero-overhead no-ops unless `AGENTLOOP_OTEL_ENDPOINT` / Langfuse
  keys are set. Each loop iteration exports a span. (#12)

- **Structured JSON logging** — `LOG_JSON=true` emits one JSON line per log
  record for Loki / Elastic / CloudWatch ingestion. (#13)

- **Cost dashboard** — `--serve` web UI gained a cost breakdown card
  (total + per-iteration bars + by-model, plain HTML/CSS), `--status` shows
  the per-iteration breakdown, and `agentloop --cost` prints a summary. (#1)

- **CLI polish** — grouped `--help`, `agentloop --examples` (lists all bundled
  examples), and `agentloop --doctor` (diagnoses missing agent CLI / verifier
  / sandbox issues with actionable fixes). Error messages across the CLI now
  include concrete fix instructions. (#14)

- **Example gallery grew to 10** — new `regex-engine` (held-out oracle with
  adversarial inputs), `csv-sorter` (property-based held-out),
  `markdown-to-html` (golden files), `sql-query-rewriter` (behavior
  equivalence), `python-type-checker` (exit-code oracle),
  `api-endpoint` (HTTP integration), and `git-history-rewriter` (fixture
  repos). Gallery: `docs/EXAMPLES.md`. (#9)

- **`mypy --strict` passes** on `agentloop/` (`.mypy.ini` + CI step).

- **Sustainment** — issue auto-label triage workflow, 48h issue-response SLA
  documented in CONTRIBUTING, `community-verifiers/` marketplace skeleton,
  and a weekly SWE-bench regression workflow with Discord alerts. (#10)

- **Docs site** — mkdocs-material configuration and docs pages
  (`mkdocs.yml`, `docs-requirements.txt`).

- **Launch assets** — technical blog post on the held-out oracle
  (`blog/2026-08-06-the-held-out-oracle.md`) and 3 launch-day social posts
  (`blog/social/`). Star-count and star-history badges in README.

### Fixed

- README/CHANGELOG no longer claim "parallel multi-agent fan-out" was already
  shipped; copy now says sequential until real parallelism landed here.
- `parse_plan_dag` now correctly parses comma-separated dependency lists
  (`depends on: #2, #3`).
- Example verify scripts use `python3 -m agentloop.oracle` (the module path)
  instead of the broken `python3 -m agentloop-oracle`.
- README's misleading "no API key needed" claim removed; GNHF comparison
  table replaced with category-defining language. (#11)

## [0.3.0] — 2026-07-19

### Added

- **Hard per-run cost cap** (`MAX_COST_USD`) — prevents runaway API bills.
  Tracks running cost in `agentloop.state.json` and aborts with `over-budget`
  status when exceeded. Add `ESTIMATED_COST_PER_ITER` env var for CLI mode;
  direct mode uses actual token counts when available. (#1)

- **Native notification adapters** — first-class Telegram, Discord, and Slack
  integrations. Set `NOTIFY_TELEGRAM_BOT_TOKEN` / `NOTIFY_TELEGRAM_CHAT_ID` /
  `NOTIFY_DISCORD_WEBHOOK_URL` / `NOTIFY_SLACK_WEBHOOK_URL` in `.env`. No
  shell scripting required. (#3)

- **`agentloop status` command** — prints a formatted summary of the latest
  run: status, iterations, elapsed time, cost, PID. (#6)

- **`agentloop serve` command** — starts a local web monitoring UI at
  `http://localhost:8080` (configurable with `--port`). Auto-refreshes every
  5s. Dark theme, live status badge, cost display. (#6)

- **Input auto-generator** (`oracle.py gen`) — automatically produces fresh
  inputs from a reference program using multiple generative strategies:
  random integers, floats, strings, and structured data. Accepts `--seed` for
  reproducibility. (#4)

- **Multi-agent fan-out** (`agentloop run plan.md`) — parses a markdown plan
  file and spawns sub-loops for each task sequentially. Supports
  GitHub-style checklists, bullet points, and heading-based tasks. (#7)

- **Smarter harness auto-detect** — `_auto_detect()` now runs a
  `--version` check and reports warnings for broken binaries. Added presets
  for `goose` and future-ready Windows path handling. (#5)

- **Input validation** — goal emptiness, dangerous-pattern warnings, and
  bounds checking on all config values (`MAX_ITERS`, `WALL_CLOCK_SEC`, etc.).
  Goal is truncated at 10,000 characters with a warning.

- **Log rotation** — `LOG_MAX_MB` env var (default 10 MB) with 3 backup
  files via Python's `RotatingFileHandler`.

- **Windows support** — `launch.ps1` and `stop.ps1` PowerShell equivalents
  for the shell launcher scripts. (#8)

- **Examples gallery** — `examples/` directory with three working verifier
  samples: tax-demo, JSON linter, and refactor-regression with held-out
  oracle. (#9)

- **CHANGELOG.md** and **`.pre-commit-config.yaml`** — ruff linting and
  formatting hooks for contributors.

- **GitHub Actions nightly workflow** — gated integration test that runs
  the full agent loop against a real harness (skipped by default). (#10)

### Changed

- `read_config()` now re-reads all notification and cost-cap env vars.
- `finish()` and `write_summary()` accept an optional `running_cost` parameter.
- `build_prompt()` accepts optional `cost_info` to inform the agent of its
  budget.
- Logging uses `RotatingFileHandler` instead of simple file append.
- Bumped version to 0.3.0.

## [0.2.0] — 2026-07-19

### Added

- Secret scrubbing: API keys / tokens never reach the agent; `ORACLE_SEAL`
  only reaches `VERIFY_CMD`.
- `.env` untracked; `.env.example` + gitignore; installable package
  (`pyproject.toml`, `agentloop` CLI).
- Direct-mode reflection control flow fixed; wall-clock uses absolute
  `started_at` across resume.
- Full-line `DONE`/`BLOCKED` matching; atomic state/summary writes;
  SIGTERM/SIGINT → STOP.
- Sandbox auto `git init` for checkpoints; graceful `stop.sh`; structured
  exit codes.
- CI workflow (Linux, Python 3.10/3.12/3.13); LICENSE; CONTRIBUTING;
  `--version`.

## [0.1.0] — 2026-07-18

### Added

- Initial prototype: CLI mode, direct mode, verification oracle, crash-safe
  resume, notification hook, scaffold command.
