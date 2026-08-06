# Changelog

All notable changes to AgentLoop are documented here.

## [0.6.0-dev] — 2026-08-06

### Added

- **Community verifiers marketplace is live** — `community-verifiers/` now
  ships **4 working verifiers**, each a copy-paste-able `verify.sh` pattern
  tagged by oracle type:
  - `filename-sanitizer` — fixture + post-conditions (`tags: fixture`)
  - `uniq-reimplementation` — byte-for-byte behavior-equivalence against a
    reference on seeded random inputs (`tags: behavior-equivalence`)
  - `roman-numeral-converter` — held-out oracle: sealed reference on ~80
    generated inputs, only 3 visible, graded on every one
    (`tags: held-out-oracle`)
  - `rpn-calculator` — property-based: seeded pairs of algebraically-equal
    RPN expressions must agree, with no reference or expected values
    (`tags: property-based`)

- **Adversarial CI check for the gallery** —
  `community-verifiers/check_verifiers.py` proves every verifier in *both*
  directions: it seeds the sandbox from the verifier's `solution/` and
  requires `verify.sh` to exit 0 (accepts correct code), then re-seeds from
  `bad-solution/` and requires exit 1 (rejects incorrect code). A mirror gate
  enforces `bad-solution/` matches `solution/` file-for-file so `verify.sh`
  genuinely runs the bad code, and exit 2 ("unable to evaluate") counts as a
  failure. Contributions that can't tell correct from incorrect fail CI.

- **Gallery docs** — the Example Gallery (`docs/EXAMPLES.md`) gained a
  "Community verifiers" section, and `community-verifiers/README.md` mirrors
  the same per-verifier summaries (oracle pattern, what it teaches, runtime,
  cost), with the gallery linked from the README.

## [0.5.0](https://github.com/instax-dutta/agentloop/compare/v0.4.0...v0.5.0) (2026-08-06)


### Features

* add seven bundled examples and first community verifier ([38a5809](https://github.com/instax-dutta/agentloop/commit/38a58092077bcd6dc0b451321003edec0104852b))
* automate releases — GitHub Releases on tags + release-please for auto version bumps ([d7dad42](https://github.com/instax-dutta/agentloop/commit/d7dad42c7576fbc5f58edb37770c5570c476a5db))
* parallel plan runner, telemetry, structured logging, CLI polish, mypy strict ([e13e73f](https://github.com/instax-dutta/agentloop/commit/e13e73f302c8639fc5b140b8e6a31008df838d59))
* switch PyPI publishing to Trusted Publishing (OIDC) - no API tokens needed ([fb8e4f9](https://github.com/instax-dutta/agentloop/commit/fb8e4f93f619291ed2e3dec002fd1fce00f9d147))


### Bug Fixes

* correct CI badge URL from saiduttaabhishekdash to instax-dutta ([4c10a39](https://github.com/instax-dutta/agentloop/commit/4c10a392f47f0a146b3f96fdfc746a5b32409c67))
* correct E2E test count from 14 to 13 ([513900a](https://github.com/instax-dutta/agentloop/commit/513900af1a498d7beb8ba7cad09f07736c9cc911))
* derive __version__ from importlib.metadata so pyproject.toml is single source of truth ([e45278d](https://github.com/instax-dutta/agentloop/commit/e45278dff2b391a64816ac7e39f70b8a3ba1f3b8))
* remove v-prefix from pip install in release body, document conventional commits ([0bc8571](https://github.com/instax-dutta/agentloop/commit/0bc857104b0fc7a0e064215b3bf6df42cd7cdf1a))
* skip CI on docs-only changes (README, CHANGELOG, etc.) ([4a52f60](https://github.com/instax-dutta/agentloop/commit/4a52f608b62b399b876979f304853bb1dfd2626c))


### Documentation

* add comparison table vs GNHF to README ([10951e4](https://github.com/instax-dutta/agentloop/commit/10951e4fc7dedd066a6a0d0b6c5660ab91175bd1))
* add comprehensive badges to README (PyPI, downloads, python versions, license) ([5ed5f46](https://github.com/instax-dutta/agentloop/commit/5ed5f46fa12915fcb16101c4911b196768ebd4b6))
* add E2E testing results table to README ([a508093](https://github.com/instax-dutta/agentloop/commit/a5080937aba037803170c924096aea3662e391e4))
* documentation site, benchmarks, blog posts, sustainment workflows ([08fcca5](https://github.com/instax-dutta/agentloop/commit/08fcca556a0dd68600fc1128e6482a113c66853f))

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
