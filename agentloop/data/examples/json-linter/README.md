# json-linter

Fixed test cases in bash.

## What it teaches

The simplest possible honest oracle: run the candidate against a fixed set of
inputs with hand-written expected outputs. No test framework, no oracle
tooling — just `bash` checks with clear PASS/FAIL lines.

## Oracle pattern

Temporary test files generated per iteration (`/tmp/valid.json`,
`/tmp/invalid.json`), then output assertions. Good when the task has a small,
well-defined contract.

## Run it

```bash
agentloop --init --example json-linter
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–2 minutes. Expected cost: < $0.10.
