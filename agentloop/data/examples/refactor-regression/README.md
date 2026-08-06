# refactor-regression

Held-out oracle — the moat.

## What it teaches

The pattern AgentLoop exists for: behavior-preserving refactoring. A trusted
reference (the original nested-if implementation) is recorded on 200 generated
inputs; the agent must refactor it and match the reference on the ~190 inputs
it never saw. Sealed with `ORACLE_SEAL` so tampering is detectable.

## Oracle pattern

`oracle.py gen` → `record` (3 visible / 197 held-out) → `grade`. Copy this for
any "make it better but don't change behaviour" task.

## Run it

```bash
agentloop --init --example refactor-regression
agentloop --verify "bash verify.sh"
```

Expected runtime: ~2–4 minutes. Expected cost: < $0.15.
