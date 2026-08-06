# csv-sorter

Held-out oracle with property-based testing.

## What it teaches

How to defeat "works on my examples" solutions with generated properties. The
verify script generates 40 random record batches — including deliberate
duplicate ids to probe sorting *stability* — and grades the agent's sorter on
cases it never saw during the visible examples.

## Oracle pattern

`agentloop-oracle record` uses Python's stable `sort` as the reference;
`grade` runs the agent's `csv_sorter.py` on the generated held-out batches.
This is the property-based testing pattern for anything with a deterministic
correct answer.

## Run it

```bash
agentloop --init --example csv-sorter
agentloop --verify "bash verify.sh"
```

Expected runtime: ~1–3 minutes. Expected cost: < $0.10.
