# AgentLoop — proposed GitHub issues (for contributors)

These are ready to create as GitHub issues once the repo is published.
Batch-create with: `gh issue create --title "..." --body "..."` (or paste into the UI).

---

## 1. Hard per-run cost cap
Today the loop is bounded by `MAX_ITERS` and `WALL_CLOCK_SEC` only. Add a
cost guard: estimate token spend per iteration (where the harness exposes it)
and abort with status `over-budget` before runaway API bills. Track running
cost in `agentloop.state.json`.

Acceptance: loop stops with `status=over-budget` when a `MAX_COST_USD` env is
exceeded; the summary reflects the spent amount.

## 2. Container / hard-isolation sandbox mode
The wrapped agent runs with `cwd=sandbox` but relies on the harness's own
permission model. Add a `--docker` mode that runs the agent CLI inside an
ephemeral, network-egress-limited container with a scoped, credential-free
token, so untrusted agents can't touch the host.

Acceptance: `agentloop --docker "goal" --verify ...` spins up a container, mounts
only `sandbox/`, and tears it down on exit.

## 3. Native notify integrations
`NOTIFY_CMD` is generic but requires the user to hand-roll curl. Add first-class
adapters for Telegram, Discord, and Slack (webhook URLs via env) that format the
terminal-state summary nicely.

Acceptance: setting `NOTIFY_TELEGRAM=https://...` delivers the run summary on
DONE/BLOCKED/STOP, no shell scripting required.

## 4. Held-out oracle UX: auto-generate fresh inputs
`oracle.py record` requires the user to supply a cases file. Add a generator
that produces fresh/metamorphic inputs from a reference program (or seeds from
the repo's existing test suite), so the held-out set is larger and harder to
overfit without manual authoring.

Acceptance: `oracle.py gen --reference ref.py --n 200 --out cases.txt` writes
inputs; `record` consumes them.

## 5. More harness presets + smarter auto-detect
Auto-detect should verify the preset binary actually runs (version check) and
report a clear error on Windows. Add presets/notes for emerging CLIs
(e.g. Codex, Goose) and document per-OS invocation quirks.

Acceptance: `_auto_detect()` warns instead of silently picking a broken binary;
Windows paths in presets are correct.

## 6. Run monitoring: `agentloop status` / web view
Add a `agentloop status` command reading `agentloop.state.json`/`summary.txt`,
and an optional tiny web view listing active/completed runs (multi-run).

Acceptance: `agentloop status` prints the latest run's status/iters/elapsed;
optional `--serve` exposes a localhost page.

## 7. Parallel / multi-agent orchestration
Support fan-out: one goal decomposed into N sub-tasks, each driven by its own
AgentLoop instance with a shared oracle, then merged.

Acceptance: `agentloop run plan.md` spins up one loop per task and reports
aggregate status.

## 8. CI + Windows support
Add a GitHub Actions workflow running `test_oracle.py` + `test_loop.py` on
push (Linux + Windows). Ensure the loop and tests pass on Windows paths.

Acceptance: green CI on PRs; Windows job exists.

## 9. Docs: CONTRIBUTING + examples gallery
Add `CONTRIBUTING.md` and an `examples/` dir with per-harness `verify.sh`
samples (tax demo, JSON linter, refactor-regression with the held-out oracle).

Acceptance: `examples/` has >=3 working verifier samples; CONTRIBUTING explains
the oracle contract.

## 10. Real-harness integration test (optional, may cost)
Add a gated CI job (manual / nightly) that runs AgentLoop against real OpenCode
on the tax demo, proving the end-to-end loop against a live agent.

Acceptance: nightly job passes; skipped by default to avoid API cost.
