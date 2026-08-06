# Concepts

## The verification oracle

AgentLoop is **not** a coding agent. It is a thin wrapper that adds a
correctness gate the agent cannot fake:

- `VERIFY_CMD` runs with `cwd` = project root (never the sandbox).
- Exit `0` means the work is **correct** — not merely that it runs.
- Failure output is fed back to the agent so every retry is informed.

## The held-out oracle (the moat)

A plain verifier can be gamed: if the agent can see your test cases, it will
fit them. AgentLoop's sealed, held-out grading defeats that:

```bash
# 1) Auto-generate fresh inputs from a reference program
agentloop-oracle gen --reference "python ref.py" --n 200 --out cases.txt --seed 42

# 2) Record the reference — split into visible + held-out (sealed)
agentloop-oracle record --reference "python ref.py" --inputs cases.txt \
  --visible 3 --out .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"

# 3) Grade the candidate on ALL inputs — it only passes on the ones it never saw
agentloop-oracle grade --candidate "python sandbox/solution.py" \
  --oracle .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
```

A wrong `--seal` reports **TAMPERED**. The held-out file lives outside the
sandbox — the agent can't read it, can't overfit to it.

## Oracle patterns

| Pattern | When | Example |
|---------|------|---------|
| Fixed test cases | Small, well-defined output | `json-linter` |
| Held-out oracle | Overfitting risk / edge cases | `regex-engine` |
| Property-based + held-out | Random inputs possible | `csv-sorter` |
| Behavior-equivalence | "Keep behaviour identical" | `sql-query-rewriter` |
| Golden files | Defined output format | `markdown-to-html` |
| Exit-code oracle | "Make it pass the linter" | `python-type-checker` |
| Integration (HTTP) | Builds a service | `api-endpoint` |
| Fixture + post-conditions | Mutates a system | `git-history-rewriter` |

## Cost tracking

CLI mode estimates cost per iteration (`ESTIMATED_COST_PER_ITER`, $0.10
default) and can parse real token usage from harness output (Claude Code JSON,
OpenCode JSON, Aider "Tokens:" lines). Direct mode tracks real token counts.
Set `MAX_COST_USD` for a guard; near the cap the prompt is injected with a
"BUDGET CRITICAL" warning.

## Isolation

| Mode | Filesystem | Network | Process | Secrets |
|------|-----------|---------|---------|---------|
| default (cwd=sandbox) | host | host | host | scrubbed |
| `--docker` | container | restricted* | container | scrubbed |
| `--podman` | container | restricted* | container | scrubbed |

\* `--network=none` by default; set `AGENTLOOP_DOCKER_NETWORK=host` for
harnesses that need model API access. Full matrix:
[Isolation](ISOLATION.md).
