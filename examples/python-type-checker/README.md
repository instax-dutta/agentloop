# python-type-checker

Exit-code oracle.

## What it teaches

The cheapest honest oracle: run a real linter/type-checker and require exit 0.
`py_compile` always; `mypy` when installed. No bespoke test logic — the
checker tool IS the oracle. Perfect for "make this code pass lint/type-check"
tasks and for verifying an agent didn't leave syntax errors behind.

## Oracle pattern

`python3 -m py_compile` + `mypy` exit codes, plus a tiny behaviour spot-check
so the agent can't just write an empty annotated stub.

## Run it

```bash
agentloop --init --example python-type-checker
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–2 minutes. Expected cost: < $0.10.
